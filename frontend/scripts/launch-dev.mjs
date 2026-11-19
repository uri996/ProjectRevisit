// Launcher-only helper. The START barrier lets Windows own the process tree first.
import { createInterface } from "node:readline";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const input = createInterface({ input: process.stdin });
let server;
let started = false;
async function stop() {
  await server?.close();
  process.exit(0);
}
input.on("close", () => void stop());
input.on("line", async (line) => {
  if (started) {
    if (line === "STOP") await stop();
    return;
  }
  if (line !== "START") return;
  started = true;
  try {
    const require = createRequire(import.meta.url);
    const manifest = JSON.parse(
      readFileSync(new URL("../package.json", import.meta.url), "utf8"),
    );
    for (const name of Object.keys(manifest.dependencies || {}))
      require.resolve(name);
    const { resolveConfig, createServer } = await import("vite");
    if (process.argv.includes("--inspect-config")) {
      const config = await resolveConfig({ logLevel: "silent" }, "serve");
      const proxy = config.server.proxy?.["/api"];
      process.stdout.write(
        "PROJECTREVISIT_CONFIG:" +
          JSON.stringify({
            host: config.server.host ?? "localhost",
            port: config.server.port ?? 5173,
            backend: typeof proxy === "string" ? proxy : proxy?.target,
          }) +
          "\n",
        () => process.exit(0),
      );
      return;
    }
    server = await createServer({
      logLevel: "silent",
      server: { host: "127.0.0.1", strictPort: true },
    });
    await server.listen();
    console.log("PROJECTREVISIT_READY");
  } catch (error) {
    console.error(
      error?.code === "EADDRINUSE" ||
        /already in use/.test(error?.message || "")
        ? "Vite port is already in use. Close the existing service before retrying."
        : "Vite startup failed. Check frontend/vite.config.ts, Node version and npm ci dependencies.",
    );
    await server?.close();
    process.exit(1);
  }
});
