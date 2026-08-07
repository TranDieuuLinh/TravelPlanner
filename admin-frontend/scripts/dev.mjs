import { existsSync, lstatSync, mkdirSync, readlinkSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawn } from "node:child_process";

const projectRoot = process.cwd();
const devOutputLink = join(projectRoot, ".next-admin-dev");
const devOutputTarget = join(tmpdir(), "travelplanner_admin_next-dev");
const nodeModules = join(projectRoot, "node_modules");
const nextCli = join(nodeModules, "next", "dist", "bin", "next");

mkdirSync(devOutputTarget, { recursive: true });

if (existsSync(devOutputLink)) {
  const isExpectedJunction =
    lstatSync(devOutputLink).isSymbolicLink() &&
    resolve(readlinkSync(devOutputLink)) === resolve(devOutputTarget);

  if (!isExpectedJunction) {
    rmSync(devOutputLink, { recursive: true, force: true });
  }
}

if (!existsSync(devOutputLink)) {
  symlinkSync(devOutputTarget, devOutputLink, "junction");
}

const child = spawn(
  process.execPath,
  [nextCli, "dev", "--turbopack", "--port", "3001"],
  {
    cwd: projectRoot,
    env: {
      ...process.env,
      NODE_PATH: nodeModules
    },
    stdio: "inherit"
  }
);

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
