import type { RequestHandler } from "express";
import { createClient } from '@supabase/supabase-js';

// Initialize Supabase client
const supabaseUrl = process.env.VITE_SUPABASE_URL || process.env.SUPABASE_URL;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.VITE_SUPABASE_ANON_KEY;

const supabase = supabaseUrl && supabaseServiceKey ? createClient(supabaseUrl, supabaseServiceKey) : null;

export const handleTrainModel: RequestHandler = async (req, res) => {
  try {
    if (!supabase) {
      return res.status(503).json({ 
        error: "Supabase not configured. ML training unavailable." 
      });
    }

    const { model_type, model_name, config, data_sources } = req.body ?? {};
    
    if (!model_type) {
      return res.status(400).json({ error: 'model_type is required' });
    }

    const mockUserId = 'anonymous-user'; // Replace with actual user authentication

    // Create ML model
    const { data: model, error: modelError } = await supabase
      .from('ml_models')
      .insert({
        name: model_name || `${model_type}_model`,
        model_type,
        configuration: config || {},
        description: `ML model for ${model_type}`,
        user_id: mockUserId
      })
      .select()
      .single();

    if (modelError) throw modelError;

    // Create training session
    const { data: session, error: sessionError } = await supabase
      .from('ml_training_sessions')
      .insert({
        model_id: model.id,
        user_id: mockUserId,
        status: 'training'
      })
      .select()
      .single();

    if (sessionError) throw sessionError;

    // Simulate training completion (in real implementation, this would be async)
    setTimeout(async () => {
      try {
        await supabase
          .from('ml_training_sessions')
          .update({
            status: 'completed',
            completed_at: new Date().toISOString(),
            metrics: { 
              accuracy: 0.85 + Math.random() * 0.1, 
              precision: 0.82 + Math.random() * 0.1, 
              recall: 0.88 + Math.random() * 0.1 
            }
          })
          .eq('id', session.id);

        await supabase
          .from('ml_models')
          .update({ is_active: true })
          .eq('id', model.id);
      } catch (error) {
        console.error('Failed to update training session:', error);
      }
    }, 2000);

    return res.json({
      success: true,
      message: 'Model training started',
      model_id: model.id,
      training_session_id: session.id
    });

  } catch (error) {
    console.error('ML training error:', error);
    return res.status(500).json({ error: 'Failed to start model training' });
  }
};

export const handleGetModels: RequestHandler = async (req, res) => {
  try {
    if (!supabase) {
      return res.status(503).json({ 
        error: "Supabase not configured. ML models unavailable." 
      });
    }

    const mockUserId = 'anonymous-user'; // Replace with actual user authentication

    const { data: models, error } = await supabase
      .from('ml_models')
      .select(`
        *,
        training_sessions:ml_training_sessions(*)
      `)
      .eq('user_id', mockUserId)
      .order('created_at', { ascending: false });

    if (error) throw error;

    const result = models?.map(model => ({
      id: model.id,
      name: model.name,
      model_type: model.model_type,
      is_active: model.is_active,
      created_at: model.created_at,
      latest_training: model.training_sessions?.[0]?.metrics || null
    })) || [];

    return res.json({
      models: result,
      available_types: ['classification', 'regression', 'clustering']
    });

  } catch (error) {
    console.error('Get models error:', error);
    return res.status(500).json({ error: 'Failed to get models' });
  }
};

export const handlePredict: RequestHandler = async (req, res) => {
  try {
    if (!supabase) {
      return res.status(503).json({ 
        error: "Supabase not configured. ML prediction unavailable." 
      });
    }

    const { model_id, input_data } = req.body ?? {};
    
    if (!model_id) {
      return res.status(400).json({ error: 'model_id is required' });
    }

    const mockUserId = 'anonymous-user'; // Replace with actual user authentication

    // Get the ML model
    const { data: model, error: modelError } = await supabase
      .from('ml_models')
      .select('*')
      .eq('id', model_id)
      .eq('user_id', mockUserId)
      .single();

    if (modelError) {
      return res.status(404).json({ error: 'Model not found' });
    }

    if (!model.is_active) {
      return res.status(400).json({ error: 'Model is not active' });
    }

    // Generate mock predictions (in real implementation, load and use trained model)
    const predictions = (input_data || [{}]).map(() => Math.random());
    const feature_importance = {
      'feature_1': 0.3,
      'feature_2': 0.25,
      'feature_3': 0.2,
      'feature_4': 0.15,
      'feature_5': 0.1
    };

    return res.json({
      success: true,
      predictions,
      feature_importance,
      model_info: {
        name: model.name,
        type: model.model_type,
        is_active: model.is_active
      }
    });

  } catch (error) {
    console.error('Prediction error:', error);
    return res.status(500).json({ error: 'Failed to make prediction' });
  }
};
