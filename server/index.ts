import "dotenv/config";
import express from "express";
import cors from "cors";
import { handleDemo } from "./routes/demo";
import { handleIngest } from "./routes/ingest";
import { handleTrainModel, handleGetModels, handlePredict } from "./routes/ml";
import { handleGenerateSchedule, handleGetScheduleHistory, handleGetScheduleDetails } from "./routes/scheduling";

export function createServer() {
  const app = express();

  // Middleware
  app.use(cors());
  app.use(express.json({ limit: "10mb" }));
  app.use(express.urlencoded({ extended: true }));

  // Example API routes
  app.get("/api/ping", (_req, res) => {
    const ping = process.env.PING_MESSAGE ?? "ping";
    res.json({ message: ping });
  });

  app.get("/api/demo", handleDemo);
  app.post("/api/ingest", handleIngest);
  
  // ML API routes
  app.post("/api/ml/train", handleTrainModel);
  app.get("/api/ml/models", handleGetModels);
  app.post("/api/ml/predict", handlePredict);

  // Scheduling API routes
  app.post("/api/schedule/generate", handleGenerateSchedule);
  app.get("/api/schedule/history", handleGetScheduleHistory);
  app.get("/api/schedule/:planning_date", handleGetScheduleDetails);

  return app;
}
