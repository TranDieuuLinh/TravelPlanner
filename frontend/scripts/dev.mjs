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
const devOutputTarget = join(tmpdir(), "travelplanner_next-dev");
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

function hasIncompleteWebpackRuntime(outputDirectory) {
  const buildManifest = join(outputDirectory, "build-manifest.json");
  if (!existsSync(buildManifest)) return false;

  const requiredBrowserChunks = [
    join(outputDirectory, "static", "chunks", "main-app.js"),
    join(outputDirectory, "static", "chunks", "app-pages-internals.js")
  ];

  if (requiredBrowserChunks.some((chunkPath) => !existsSync(chunkPath))) {
    return true;
  }

  const documentBundle = join(
    outputDirectory,
    "server",
    "pages",
    "_document.js"
  );
  if (!existsSync(documentBundle)) return false;

  const documentSource = readFileSync(documentBundle, "utf8");
  const documentEntry = documentSource.match(/__webpack_exec__\(["']([^"']+)["']\)/);
  const documentChunks = documentSource.match(
    /__webpack_require__\.X\(0,\s*\[([^\]]*)\]/
  );
  if (!documentEntry || !documentChunks) return false;

  const requiredServerChunks = Array.from(
    documentChunks[1].matchAll(/["']([^"']+)["']/g),
    (match) => match[1]
  );
  const entryModuleMarker = `/***/ "${documentEntry[1]}":`;

  return !requiredServerChunks.some((chunkId) => {
    const chunkPath = join(outputDirectory, "server", `${chunkId}.js`);
    return (
      existsSync(chunkPath) &&
      readFileSync(chunkPath, "utf8").includes(entryModuleMarker)
    );
  });
}

if (
  hasBrokenTurbopackRuntime(devOutputTarget) ||
  hasIncompleteWebpackRuntime(devOutputTarget)
) {
  console.warn("Detected an incomplete Next dev cache; rebuilding it.");
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

// Turbopack cuts route compilation time substantially for the large planner
// client bundle. The cache checks above repair the incomplete-runtime case;
// set NEXT_USE_TURBOPACK=0 only when debugging a bundler-specific issue.
const devArgs = [nextCli, "dev"];
if (process.env.NEXT_USE_TURBOPACK !== "0") devArgs.push("--turbopack");
const child = spawn(process.execPath, devArgs, {
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
