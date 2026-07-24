#!/usr/bin/env node
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import {
  access,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { basename, join, relative, resolve } from "node:path";

const root = process.cwd();
const command = process.argv[2] ?? "validate";
const check = process.argv.includes("--check");
const manifestPath = join(root, "portfolio", "project.json");
const architecturePath = join(root, "architecture", "system.mmd");
const assetRoot = join(root, "portfolio", "assets");
const svgPath = join(assetRoot, "system.svg");
const pngPath = join(assetRoot, "system.png");
const freshnessPath = join(assetRoot, "system.freshness.json");
const technologyIndexPath = join(assetRoot, "technology", "index.json");
const readmePath = join(root, "README.md");
const rendererVersion = "@mermaid-js/mermaid-cli@11.12.0";

function hash(value) {
  return createHash("sha256").update(value).digest("hex");
}

function text(value, fallback = "Not recorded") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function inline(value) {
  return text(value).replaceAll("|", "\\|").replaceAll("\n", " ");
}

function list(values, fallback = ["Not recorded."]) {
  return (values?.length ? values : fallback).map((value) => `- ${value}`).join("\n");
}

function table(headers, rows) {
  return [
    `| ${headers.join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
    ...rows.map((row) => `| ${row.map(inline).join(" | ")} |`),
  ].join("\n");
}

function fenced(commandText) {
  return `\`\`\`bash\n${commandText}\n\`\`\``;
}

async function loadManifest() {
  return JSON.parse(await readFile(manifestPath, "utf8"));
}

async function loadTechnologyIndex() {
  try {
    return JSON.parse(await readFile(technologyIndexPath, "utf8"));
  } catch {
    return { technologies: [] };
  }
}

function evidenceMap(manifest) {
  return new Map((manifest.evidence ?? []).map((item) => [item.id, item]));
}

function evidenceLinks(refs, catalog) {
  return (refs ?? []).map((id) => {
    const item = catalog.get(id);
    return item ? `[${id}](${item.source})` : `\`${id}\``;
  }).join(", ") || "Not recorded";
}

function renderReadme(manifest, technologies) {
  const presentation = manifest.presentation ?? {};
  const story = manifest.story ?? {};
  const evidence = evidenceMap(manifest);
  const repo = manifest.githubUrl?.replace(/^https:\/\/github\.com\//, "").replace(/\/$/, "");
  const badges = [
    repo ? `[![CI](https://github.com/${repo}/actions/workflows/ci.yml/badge.svg)](https://github.com/${repo}/actions/workflows/ci.yml)` : null,
    `![Publication](https://img.shields.io/badge/publication-${presentation.publicationStatus ?? "review_required"}-5b6470)`,
    `![Production claim](https://img.shields.io/badge/production_claim-${manifest.deployment?.productionClaim ? "yes" : "no"}-${manifest.deployment?.productionClaim ? "b42318" : "18794e"})`,
  ].filter(Boolean).join(" ");

  const techRows = technologies.technologies.map((item) => [
    item.icon
      ? `<img src="${item.icon}" width="20" height="20" alt="" /> ${item.name}`
      : item.name,
    item.role ?? "Project technology",
    item.provenance ?? "Text fallback",
  ]);
  const decisionRows = (story.technologyDecisions ?? []).map((item) => [
    item.technology,
    item.rationale,
    item.alternative,
    item.tradeoff,
  ]);
  const evaluationRows = (story.evidence ?? []).map((item) => {
    const refs = (item.evidenceRefs ?? []).map((id) => evidence.get(id)).filter(Boolean);
    const detail = refs[0] ?? {};
    return [
      `${item.label}: ${item.value}`,
      detail.scope ?? item.context,
      detail.method ?? item.method,
      evidenceLinks(item.evidenceRefs, evidence),
      detail.caveat ?? story.limitations?.[0] ?? "See limitations.",
    ];
  });
  const disclosure = manifest.dataDisclosure ?? {};
  const securityRows = (presentation.securityControls ?? []).map((item) => [
    item.control,
    item.implementation,
    evidenceLinks(item.evidenceRefs, evidence),
    item.limitation,
  ]);
  const costRows = (presentation.costBoundaries ?? []).map((item) => [
    item.component,
    item.boundary,
    item.implication,
  ]);
  const structureRows = (presentation.repositoryStructure ?? []).map((item) => [
    `\`${item.path}\``,
    item.purpose,
  ]);
  const verificationRows = (presentation.verification ?? []).map((item) => [
    item.check,
    `\`${item.command}\``,
    item.evidenceRef ? evidenceLinks([item.evidenceRef], evidence) : "Command output",
  ]);
  const deploymentRows = [[
    manifest.deployment?.provider,
    manifest.deployment?.runtime,
    manifest.deployment?.status,
    manifest.deployment?.exposure,
    manifest.deployment?.verifiedAt,
    manifest.deployment?.productionClaim ? "Yes" : "No",
  ]];

  return `# ${manifest.title}

${badges}

> ${manifest.summary}

## Executive overview

${table(
    ["Question", "Reviewed fact"],
    [
      ["Problem", presentation.question ?? manifest.outcome],
      ["Intended user", story.intendedUser],
      ["Decision supported", presentation.decisionSupported ?? story.example?.title],
      ["Outcome", manifest.outcome],
      ["Try it", manifest.liveUrl ? `[Open the reviewed demo](${manifest.liveUrl})` : "No public demo is claimed."],
      ["Important boundary", manifest.disclaimer],
    ],
  )}

## What the system does

${list(manifest.stages)}

## Visual architecture

![${presentation.architectureAlt ?? `${manifest.title} system architecture showing actors, processing, data boundaries, controls, deployment, outputs, and evidence flow.`}](portfolio/assets/system.svg)

Canonical editable source: [\`architecture/system.mmd\`](architecture/system.mmd). The SVG and PNG are deterministic generated assets; \`system.freshness.json\` records their source hash and renderer.

## End-to-end workflow

${list(story.example?.steps ?? manifest.stages)}

## Technology stack

${table(["Technology", "Role", "Asset provenance"], techRows)}

## Quick start

${(presentation.quickStart ?? []).map((item) => `### ${item.label}\n\n${fenced(item.command)}`).join("\n\n") || "Project-specific setup commands have not been recorded."}

## Demonstration workflow

${story.example ? `**${story.example.title}**\n\n${list(story.example.steps)}` : "No demonstration workflow is claimed."}

## Evaluation

${table(["Measure", "Dataset / scope", "Method", "Evidence", "Limitation"], evaluationRows)}

Evaluation mode: **${presentation.evaluationMode ?? "See each evidence record"}**. These results are project evidence, not a production SLO.

## Data disclosure

${table(
    ["Classification", "Source", "Permitted use", "Excluded data"],
    [[disclosure.classification, disclosure.source, disclosure.permittedUse, (disclosure.excludedFields ?? []).join("; ")]],
  )}

License / provenance: ${text(disclosure.license)}

## Security and privacy boundaries

${table(["Control", "Implementation", "Evidence", "Known limitation"], securityRows)}

## Deployment state

${table(["Provider", "Runtime", "State", "Exposure", "Verified", "Production claim"], deploymentRows)}

## Technology decisions and trade-offs

${table(["Decision", "Why", "Alternative", "Trade-off"], decisionRows)}

## Cost boundaries

${table(["Component", "Boundary", "Implication"], costRows)}

## Known limitations

${list(story.limitations ?? manifest.operationalTradeoffs)}

## Scalability roadmap

${list(story.scalabilityRoadmap)}

## Repository structure

${table(["Path", "Purpose"], structureRows)}

## Reproduction and verification

${table(["Check", "Command", "Evidence"], verificationRows)}

## Evidence index

${table(
    ["ID", "Kind", "Claim", "Method", "Result"],
    (manifest.evidence ?? []).map((item) => [
      `[\`${item.id}\`](${item.source})`,
      item.kind,
      item.claim,
      item.method,
      item.result,
    ]),
  )}

## License and attribution

${presentation.licenseNote ?? "See the repository license for source-code terms."}

Technology marks are local copies generated from the pinned Simple Icons package where a canonical mark is available; every mark has a visible text label. Mermaid-generated architecture assets are derived from the canonical source in this repository.
`;
}

async function findExecutable(directory, target) {
  try {
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      const path = join(directory, entry.name);
      if (entry.isFile() && entry.name === target) return path;
      if (entry.isDirectory()) {
        const found = await findExecutable(path, target);
        if (found) return found;
      }
    }
  } catch {
    return null;
  }
  return null;
}

async function mermaidCommand() {
  const local = join(root, "node_modules", ".bin", "mmdc");
  try {
    await access(local);
    return { executable: local, prefix: [] };
  } catch {
    try {
      return { executable: execFileSync("sh", ["-c", "command -v mmdc"], { encoding: "utf8" }).trim(), prefix: [] };
    } catch {
      return { executable: "npx", prefix: ["--yes", rendererVersion] };
    }
  }
}

async function renderArchitecture(manifest) {
  const source = await readFile(architecturePath, "utf8");
  const sourceSha256 = hash(source);
  const work = await mkdtemp(join(tmpdir(), "portfolio-architecture-"));
  const configPath = join(work, "mermaid-config.json");
  await writeFile(configPath, `${JSON.stringify({
    theme: "base",
    themeVariables: {
      background: "#ffffff",
      primaryColor: "#eef3f8",
      primaryTextColor: "#17202a",
      primaryBorderColor: "#52606d",
      lineColor: "#334e68",
      secondaryColor: "#e8f1ff",
      tertiaryColor: "#f7f9fc",
      fontFamily: "Arial, Helvetica, sans-serif",
      fontSize: "16px",
    },
    flowchart: { curve: "basis", htmlLabels: false, nodeSpacing: 38, rankSpacing: 52 },
  }, null, 2)}\n`);
  await mkdir(assetRoot, { recursive: true });
  const commandInfo = await mermaidCommand();
  const chrome = process.env.PUPPETEER_EXECUTABLE_PATH
    ?? await findExecutable(join(homedir(), ".cache", "puppeteer", "chrome-headless-shell"), "chrome-headless-shell");
  const env = { ...process.env, ...(chrome ? { PUPPETEER_EXECUTABLE_PATH: chrome } : {}) };
  const common = ["-i", architecturePath, "--configFile", configPath, "--backgroundColor", "white", "--quiet"];
  for (const [output, extra] of [[svgPath, []], [pngPath, ["--width", "1600", "--scale", "2"]]]) {
    const result = spawnSync(commandInfo.executable, [...commandInfo.prefix, ...common, "-o", output, ...extra], {
      cwd: root,
      encoding: "utf8",
      env,
    });
    if (result.status !== 0) throw new Error(result.stderr || result.stdout || "Mermaid rendering failed");
  }
  let svg = await readFile(svgPath, "utf8");
  const alt = manifest.presentation?.architectureAlt ?? `${manifest.title} system architecture`;
  svg = svg.replace(
    /<svg\b/,
    `<svg role="img" aria-labelledby="architecture-title architecture-description" data-source-sha256="${sourceSha256}"`,
  ).replace(
    /(<svg\b[^>]*>)/,
    `$1<title id="architecture-title">${manifest.title} architecture</title><desc id="architecture-description">${alt}</desc>`,
  );
  await writeFile(svgPath, `<!-- Generated from architecture/system.mmd; source-sha256=${sourceSha256}; renderer=${rendererVersion} -->\n${svg}`);
  const freshness = {
    schemaVersion: 1,
    source: relative(root, architecturePath),
    sourceSha256,
    renderer: rendererVersion,
    svg: { path: relative(root, svgPath), sha256: hash(await readFile(svgPath)) },
    png: { path: relative(root, pngPath), sha256: hash(await readFile(pngPath)) },
  };
  await writeFile(freshnessPath, `${JSON.stringify(freshness, null, 2)}\n`);
  await rm(work, { recursive: true, force: true });
  return freshness;
}

async function validateArchitecture() {
  const source = await readFile(architecturePath, "utf8");
  const freshness = JSON.parse(await readFile(freshnessPath, "utf8"));
  const issues = [];
  if (!source.includes("Legend")) issues.push("architecture/system.mmd must include a visible Legend");
  if (!source.includes("subgraph")) issues.push("architecture/system.mmd must include at least one bounded container");
  if (freshness.sourceSha256 !== hash(source)) issues.push("architecture assets are stale");
  if (freshness.svg.sha256 !== hash(await readFile(svgPath))) issues.push("system.svg hash does not match freshness metadata");
  if (freshness.png.sha256 !== hash(await readFile(pngPath))) issues.push("system.png hash does not match freshness metadata");
  if (issues.length) throw new Error(issues.join("; "));
  return freshness;
}

async function validateHygiene() {
  const tracked = execFileSync("git", ["ls-files"], { cwd: root, encoding: "utf8" }).split("\n").filter(Boolean);
  const vendorFiles = tracked.filter((path) => path === "CLAUDE.md" || path.startsWith(".claude/"));
  if (vendorFiles.length) throw new Error(`vendor-specific files remain tracked: ${vendorFiles.join(", ")}`);
}

async function writeOrCheckReadme(manifest) {
  const technologyIndex = await loadTechnologyIndex();
  const generated = renderReadme(manifest, technologyIndex);
  if (check) {
    const current = await readFile(readmePath, "utf8");
    if (current !== generated) throw new Error("README.md is stale; run `node scripts/project-presentation.mjs readme`");
  } else {
    await writeFile(readmePath, generated);
  }
}

async function validate() {
  const manifest = await loadManifest();
  if (manifest.version !== 2) throw new Error("portfolio/project.json must use manifest v2");
  await writeOrCheckReadme(manifest);
  await validateArchitecture();
  await validateHygiene();
  const technologyIndex = await loadTechnologyIndex();
  const names = new Set(technologyIndex.technologies.map((item) => item.name));
  const missing = (manifest.stack ?? []).filter((name) => !names.has(name));
  if (missing.length) throw new Error(`technology identity missing for: ${missing.join(", ")}`);
  console.log(`${manifest.slug}: presentation contract passes.`);
}

if (command === "architecture") {
  const manifest = await loadManifest();
  if (check) await validateArchitecture();
  else await renderArchitecture(manifest);
} else if (command === "readme") {
  await writeOrCheckReadme(await loadManifest());
} else if (command === "validate") {
  await validate();
} else {
  throw new Error("Usage: project-presentation.mjs architecture|readme|validate [--check]");
}
