import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const builds = [
  ["frontend", ".next-verify"],
  ["admin-frontend", ".next-admin-verify"]
];

for (const [workspace, distDir] of builds) {
  const isWindows = process.platform === "win32";
  const command = isWindows ? process.env.ComSpec ?? "cmd.exe" : "npm";
  const args = isWindows
    ? ["/d", "/s", "/c", `npm run build --workspace ${workspace}`]
    : ["run", "build", "--workspace", workspace];
  const result = spawnSync(
    command,
    args,
    {
      cwd: root,
      env: { ...process.env, NEXT_DIST_DIR: distDir },
      stdio: "inherit"
    }
  );

  if (result.error) {
    console.error(`Could not start npm for ${workspace}:`, result.error);
    process.exit(1);
  }

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}
