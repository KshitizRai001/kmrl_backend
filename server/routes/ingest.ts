import type { RequestHandler } from "express";
import { createClient } from '@supabase/supabase-js';

// Initialize Supabase client
const supabaseUrl = process.env.VITE_SUPABASE_URL || process.env.SUPABASE_URL;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseServiceKey) {
  console.warn('Supabase configuration missing. CSV ingestion will use local processing.');
}

const supabase = supabaseUrl && supabaseServiceKey ? createClient(supabaseUrl, supabaseServiceKey) : null;

export const handleIngest: RequestHandler = async (req, res) => {
  try {
    const { source, fileName, count, headers, rows } = req.body ?? {};
    if (!source || !Array.isArray(rows)) {
      return res.status(400).json({ message: "Invalid payload" });
    }

    // Try to store in Supabase if configured
    if (supabase) {
      try {
        // Note: In a real implementation, you'd get the user ID from the JWT token
        // For now, we'll create a mock user ID or handle it differently
        const mockUserId = 'anonymous-user'; // This should be replaced with actual user authentication

        // Get or create data source
        let { data: dataSource, error: sourceError } = await supabase
          .from('csv_data_sources')
          .select('*')
          .eq('name', source)
          .single();

        if (sourceError && sourceError.code === 'PGRST116') {
          // Data source doesn't exist, create it
          const { data: newSource, error: createError } = await supabase
            .from('csv_data_sources')
            .insert({
              name: source,
              description: `Data source for ${source}`
            })
            .select()
            .single();

          if (createError) throw createError;
          dataSource = newSource;
        } else if (sourceError) {
          throw sourceError;
        }

        // Create CSV upload record
        const { data: upload, error: uploadError } = await supabase
          .from('csv_uploads')
          .insert({
            source_id: dataSource!.id,
            filename: fileName || 'unknown.csv',
            row_count: rows.length,
            headers: headers || [],
            user_id: mockUserId
          })
          .select()
          .single();

        if (uploadError) throw uploadError;

        // Insert data rows in batches
        const batchSize = 100;
        for (let i = 0; i < rows.length; i += batchSize) {
          const batch = rows.slice(i, i + batchSize).map((row: any, index: number) => ({
            upload_id: upload.id,
            row_data: row,
            row_index: i + index
          }));

          const { error: rowError } = await supabase
            .from('csv_data_rows')
            .insert(batch);

          if (rowError) throw rowError;
        }

        return res.json({
          message: `Successfully ingested ${rows.length} rows from ${fileName || 'CSV file'}`,
          upload_id: upload.id,
          headers: Array.from(new Set(headers || [])),
          sample: rows.slice(0, 3),
        });

      } catch (supabaseError) {
        console.warn("Supabase storage failed:", supabaseError);
        // Fall through to local processing
      }
    }

    // Fallback to local processing
    return res.json({
      message: `Received ${count ?? rows.length} rows for ${source}${fileName ? ` from ${fileName}` : ""} (local processing).`,
      headers: Array.from(new Set(headers || [])),
      sample: rows.slice(0, 3),
      warning: "Stored locally - Supabase not configured or unavailable"
    });

  } catch (e) {
    return res.status(500).json({ message: (e as Error).message });
  }
};
