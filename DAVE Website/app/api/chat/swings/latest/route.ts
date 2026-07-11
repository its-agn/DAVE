import path from "path";
import fs from "fs/promises";
import { NextResponse } from "next/server";

export const runtime = "nodejs";

// process.cwd() is the Next.js project root (DAVE Website/) when the dev/prod
// server is started from there, so this resolves to DAVE Website/data.
const dataRoot = path.join(process.cwd(), "data");

export async function GET() {
  try {
    const latestPath = path.join(dataRoot, "latest.json");

    let latestRaw: string;
    try {
      latestRaw = await fs.readFile(latestPath, "utf8");
    } catch (e) {
      // No swing has ever been processed yet — this is an expected state,
      // not a server error, so we return 404 with a clear status field
      // rather than a generic 500.
      return NextResponse.json(
        { status: "no_data", error: "No swing data available yet." },
        { status: 404 }
      );
    }

    let latest: any;
    try {
      latest = JSON.parse(latestRaw);
    } catch (e) {
      console.error("latest.json contains invalid JSON", e);
      return NextResponse.json(
        { error: "latest.json is corrupted." },
        { status: 500 }
      );
    }

    if (latest.status !== "complete" || !latest.swing_file) {
      // Nothing new/ready yet — hand back the raw status so the client can
      // decide how to render a "waiting" state.
      return NextResponse.json(latest);
    }

    const swingPath = path.join(dataRoot, latest.swing_file);

    let swingRaw: string;
    try {
      swingRaw = await fs.readFile(swingPath, "utf8");
    } catch (e) {
      // latest.json points at a swing_file that isn't readable. Per the
      // atomicity guarantee this shouldn't happen, but guard anyway.
      console.error(`Failed to read swing file at ${swingPath}`, e);
      return NextResponse.json(
        { error: "Swing metadata found but swing file missing or unreadable." },
        { status: 500 }
      );
    }

    let swing: any;
    try {
      swing = JSON.parse(swingRaw);
    } catch (e) {
      console.error(`Swing file at ${swingPath} contains invalid JSON`, e);
      return NextResponse.json(
        { error: "Swing file is corrupted." },
        { status: 500 }
      );
    }

    return NextResponse.json({
      ...latest,
      swing,
    });
  } catch (error) {
    console.error("Error in /api/swings/latest", error);
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Failed to read latest swing.",
      },
      { status: 500 }
    );
  }
}
