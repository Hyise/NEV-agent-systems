import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const failures = [];

function read(relativePath) {
  const absolutePath = resolve(frontendRoot, relativePath);
  if (!existsSync(absolutePath)) {
    failures.push(`${relativePath}: file is missing`);
    return "";
  }
  return readFileSync(absolutePath, "utf8");
}

function expectContains(relativePath, values) {
  const content = read(relativePath);
  for (const value of values) {
    if (!content.includes(value)) {
      failures.push(
        `${relativePath}: expected to contain ${JSON.stringify(value)}`,
      );
    }
  }
}

function expectNotContains(relativePath, values) {
  const content = read(relativePath);
  for (const value of values) {
    if (content.includes(value)) {
      failures.push(
        `${relativePath}: expected not to contain ${JSON.stringify(value)}`,
      );
    }
  }
}

const styleLayers = [
  "./styles/foundation.css",
  "./styles/shell.css",
  "./styles/components.css",
  "./styles/pages.css",
];

const entryPath = "src/style.css";
const entry = read(entryPath);
let previousIndex = -1;

for (const layer of styleLayers) {
  const importStatement = `@import \"${layer}\";`;
  const index = entry.indexOf(importStatement);
  if (index === -1) {
    failures.push(`${entryPath}: missing ${importStatement}`);
  } else if (index < previousIndex) {
    failures.push(`${entryPath}: imports must follow the declared layer order`);
  }
  previousIndex = index;
  read(`src/${layer.slice(2)}`);
}

expectNotContains(entryPath, [":root {", ".app-shell {", ".panel {"]);
expectContains("package.json", [
  '"check:design": "node scripts/check-design-contract.mjs"',
]);

if (failures.length > 0) {
  console.error(
    "Design contract failed:\n" +
      failures.map((item) => `- ${item}`).join("\n"),
  );
  process.exit(1);
}

console.log("Design contract passed.");
