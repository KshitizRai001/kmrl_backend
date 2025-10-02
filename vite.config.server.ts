import { defineConfig } from "vite";
import path from "path";

export default defineConfig({
  build: {
    lib: {
      entry: path.resolve(__dirname, "server/node-build.ts"),
      name: "server",
      fileName: "server", // This ensures the output is server.mjs
      formats: ["es"],
    },
    outDir: "dist/server",
    target: "node22",
    rollupOptions: {
      external: [
        "express",
        "@supabase/supabase-js",
      ],
    },
  },
});