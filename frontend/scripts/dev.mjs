import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readlinkSync,
  rmSync,
  symlinkSync
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawn } from "node:child_process";

const projectRoot = process.cwd();
const devOutputLink = join(projectRoot, ".next-dev");
const devOutputTarget = join(tmpdir(), "VSF_TravelPlanner_next-dev");
const nodeModules = join(projectRoot, "node_modules");
const nextCli = join(nodeModules, "next", "dist", "bin", "next");

function hasFileSystemEntry(path) {
  try {
    lstatSync(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

function hasBrokenTurbopackRuntime(outputDirectory) {
  const documentBundle = join(
    outputDirectory,
    "server",
    "pages",
    "_document.js"
  );
  if (!existsSync(documentBundle)) return false;

  const bundleSource = readFileSync(documentBundle, "utf8");
  const runtimeImport = bundleSource.match(
    /require\(["']([^"']*\[turbopack\]_runtime\.js)["']\)/
  );
  if (!runtimeImport) return false;

  return !existsSync(resolve(dirname(documentBundle), runtimeImport[1]));
}

if (hasBrokenTurbopackRuntime(devOutputTarget)) {
  console.warn("Detected an incomplete Turbopack cache; rebuilding it.");
  rmSync(devOutputTarget, { recursive: true, force: true });
}

mkdirSync(devOutputTarget, { recursive: true });

if (hasFileSystemEntry(devOutputLink)) {
  const isExpectedJunction =
    lstatSync(devOutputLink).isSymbolicLink() &&
    resolve(readlinkSync(devOutputLink)) === resolve(devOutputTarget);

  if (!isExpectedJunction) {
    rmSync(devOutputLink, { recursive: true, force: true });
  }
}

if (!hasFileSystemEntry(devOutputLink)) {
  symlinkSync(devOutputTarget, devOutputLink, "junction");
}

const child = spawn(process.execPath, [nextCli, "dev", "--turbopack"], {
  cwd: projectRoot,
  env: {
    ...process.env,
    NODE_PATH: nodeModules
  },
  stdio: "inherit"
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
