import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

// Dev-time MCP server for the grounded-rag-assistant repo.
// It gives Claude Code structured, filtered context so it does not have to read
// many files or load huge logs/reports into the conversation.

const root = path.resolve(process.env.PROJECT_ROOT ?? process.cwd());

const server = new McpServer({
  name: "project-context",
  version: "0.1.0"
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function safePath(relativePath: string): string {
  const resolved = path.resolve(root, relativePath);
  if (resolved !== root && !resolved.startsWith(root + path.sep)) {
    throw new Error(`Path escapes project root: ${relativePath}`);
  }
  return resolved;
}

function ok(data: unknown) {
  return {
    structuredContent: data as Record<string, unknown>,
    content: [
      {
        type: "text" as const,
        text: JSON.stringify(data, null, 2)
      }
    ]
  };
}

function toolError(
  errorCategory: "transient" | "validation" | "permission" | "business",
  isRetryable: boolean,
  message: string,
  details: Record<string, unknown> = {}
) {
  const data = { errorCategory, isRetryable, message, details };
  return {
    isError: true,
    structuredContent: data as Record<string, unknown>,
    content: [
      {
        type: "text" as const,
        text: JSON.stringify(data, null, 2)
      }
    ]
  };
}

const ignoredDirs = new Set([
  ".git",
  "node_modules",
  "dist",
  "build",
  "coverage",
  ".next",
  ".turbo",
  ".cache",
  ".venv",
  "__pycache__",
  ".pytest_cache",
  ".ruff_cache"
]);

async function walkDirectory(
  absoluteDir: string,
  depth: number,
  maxDepth: number,
  results: string[]
): Promise<void> {
  if (depth > maxDepth) return;

  let entries;
  try {
    entries = await readdir(absoluteDir, { withFileTypes: true });
  } catch {
    return;
  }

  for (const entry of entries) {
    if (ignoredDirs.has(entry.name)) continue;

    const absolutePath = path.join(absoluteDir, entry.name);
    const relativePath = path.relative(root, absolutePath);

    if (entry.isDirectory()) {
      results.push(relativePath + "/");
      await walkDirectory(absolutePath, depth + 1, maxDepth, results);
    } else {
      results.push(relativePath);
    }
  }
}

// Recursively collect leaf values whose key looks like an eval metric. This lets
// the eval-report tool surface highlights without depending on an exact schema.
const METRIC_KEY = /precision|recall|mrr|ndcg|latency|citation|threshold|regression|p50|p95|score/i;

function collectMetricHighlights(
  node: unknown,
  prefix: string,
  out: Record<string, unknown>,
  depth: number
): void {
  if (depth > 6 || node === null || node === undefined) return;
  if (Array.isArray(node)) {
    node.forEach((item, i) => collectMetricHighlights(item, `${prefix}[${i}]`, out, depth + 1));
    return;
  }
  if (typeof node === "object") {
    for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
      const keyPath = prefix ? `${prefix}.${key}` : key;
      if (METRIC_KEY.test(key) && (typeof value === "number" || typeof value === "string" || typeof value === "boolean")) {
        out[keyPath] = value;
      }
      collectMetricHighlights(value, keyPath, out, depth + 1);
    }
  }
}

// ---------------------------------------------------------------------------
// Tool: project_snapshot
// ---------------------------------------------------------------------------

server.registerTool(
  "project_snapshot",
  {
    description:
      "Returns a compact file tree of the grounded-rag-assistant repository for orientation before code exploration. Use this when Claude needs to understand the repository layout, identify likely entry points, or plan an investigation. Do not use it to read source-code contents; use Claude Code Read/Grep/Glob for exact code. The tool filters common build, dependency, virtualenv, and cache directories to keep context small.",
    inputSchema: {
      maxDepth: z
        .number()
        .int()
        .min(1)
        .max(4)
        .default(2)
        .describe("Maximum directory depth to include, from 1 to 4.")
    }
  },
  async ({ maxDepth }) => {
    const files: string[] = [];
    await walkDirectory(root, 0, maxDepth, files);

    return ok({
      root,
      maxDepth,
      count: files.length,
      files: files.slice(0, 500),
      truncated: files.length > 500
    });
  }
);

// ---------------------------------------------------------------------------
// Tool: read_project_doc
// ---------------------------------------------------------------------------

server.registerTool(
  "read_project_doc",
  {
    description:
      "Reads a project documentation file and returns a bounded amount of text. Use this for README files, architecture notes, runbooks, ADRs, the build-phase definitions in docs/BUILD_PHASES.md, and other Claude-facing project docs. Do not use this for arbitrary source-code files; Claude Code Read is better for source code because it can inspect exact line context. The path must be relative to the repository root and must not escape the project.",
    inputSchema: {
      path: z
        .string()
        .describe("Relative path to a Markdown, text, or documentation file.")
    }
  },
  async ({ path: relativePath }) => {
    if (!/\.(md|mdx|txt|rst|adoc)$/i.test(relativePath)) {
      return toolError("validation", false, "Only documentation files are allowed.", {
        path: relativePath
      });
    }

    let text: string;
    try {
      const absolutePath = safePath(relativePath);
      const fileStat = await stat(absolutePath);
      if (!fileStat.isFile()) {
        return toolError("validation", false, "Path is not a file.", { path: relativePath });
      }
      text = await readFile(absolutePath, "utf8");
    } catch (error) {
      return toolError("validation", false, "Could not read documentation file.", {
        path: relativePath,
        error: error instanceof Error ? error.message : String(error)
      });
    }

    const maxChars = 40000;
    return ok({
      path: relativePath,
      text: text.slice(0, maxChars),
      truncated: text.length > maxChars,
      originalCharacters: text.length
    });
  }
);

// ---------------------------------------------------------------------------
// Tool: summarize_ci_failure
// ---------------------------------------------------------------------------

server.registerTool(
  "summarize_ci_failure",
  {
    description:
      "Summarizes a CI, test, lint, or build log into actionable failure facts. Use this when a pytest run, ruff check, or `make eval` produces a long log and Claude needs the error messages, failing files, and likely next debugging steps. This tool summarizes a log supplied by the caller; it does not run CI. It trims noisy output while preserving commands, stack traces, assertion failures, and file paths.",
    inputSchema: {
      log: z.string().describe("Raw CI, test, or build failure log."),
      maxLines: z
        .number()
        .int()
        .min(20)
        .max(300)
        .default(120)
        .describe("Maximum number of relevant lines to return.")
    }
  },
  async ({ log, maxLines }) => {
    const interesting = log
      .split(/\r?\n/)
      .filter((line) =>
        /error|failed|failure|exception|traceback|assert|expected|received|panic|fatal|warning|\.py|\.ts|\.tsx|\.js/i.test(
          line
        )
      )
      .slice(0, maxLines);

    return ok({
      relevantLines: interesting,
      lineCount: interesting.length,
      truncated: interesting.length >= maxLines
    });
  }
);

// ---------------------------------------------------------------------------
// Tool: eval_report_summary  (RAG-specific)
// ---------------------------------------------------------------------------

server.registerTool(
  "eval_report_summary",
  {
    description:
      "Summarizes a grounded-rag-assistant evaluation report from the eval_reports/ directory. Use this after `make eval` to read retrieval metrics (Precision@k, Recall@k, MRR, nDCG@k across bm25/vector/hybrid/rerank), citation accuracy, insufficient-evidence accuracy, latency p50/p95, and the regression-threshold status — without loading the full JSON report into the conversation. Pass no arguments to summarize the most recent report. This tool reads reports already written to disk; it does not run the evaluation harness.",
    inputSchema: {
      reportFile: z
        .string()
        .optional()
        .describe(
          "Optional relative path to a specific report JSON file. If omitted, the most recently modified file in eval_reports/ is used."
        ),
      maxChars: z
        .number()
        .int()
        .min(2000)
        .max(60000)
        .default(20000)
        .describe("Maximum characters of the raw report body to include.")
    }
  },
  async ({ reportFile, maxChars }) => {
    let absolutePath: string;

    try {
      if (reportFile) {
        absolutePath = safePath(reportFile);
      } else {
        const dir = safePath("eval_reports");
        let entries;
        try {
          entries = await readdir(dir, { withFileTypes: true });
        } catch {
          return toolError(
            "business",
            false,
            "No eval_reports/ directory found. Run `make eval` first.",
            { lookedIn: "eval_reports/" }
          );
        }
        const jsonFiles = entries.filter((e) => e.isFile() && e.name.endsWith(".json"));
        if (jsonFiles.length === 0) {
          return toolError("business", false, "No JSON reports in eval_reports/. Run `make eval` first.");
        }
        const withMtime = await Promise.all(
          jsonFiles.map(async (e) => {
            const p = path.join(dir, e.name);
            const s = await stat(p);
            return { p, mtime: s.mtimeMs };
          })
        );
        withMtime.sort((a, b) => b.mtime - a.mtime);
        absolutePath = withMtime[0].p;
      }
    } catch (error) {
      return toolError("validation", false, "Could not locate an eval report.", {
        error: error instanceof Error ? error.message : String(error)
      });
    }

    let raw: string;
    try {
      raw = await readFile(absolutePath, "utf8");
    } catch (error) {
      return toolError("validation", false, "Could not read the eval report.", {
        path: path.relative(root, absolutePath),
        error: error instanceof Error ? error.message : String(error)
      });
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      // Not valid JSON — return a bounded raw view so Claude can still inspect it.
      return ok({
        reportPath: path.relative(root, absolutePath),
        parsed: false,
        note: "Report is not valid JSON; returning a truncated raw view.",
        raw: raw.slice(0, maxChars),
        truncated: raw.length > maxChars
      });
    }

    const highlights: Record<string, unknown> = {};
    collectMetricHighlights(parsed, "", highlights, 0);

    return ok({
      reportPath: path.relative(root, absolutePath),
      parsed: true,
      metricHighlights: highlights,
      highlightCount: Object.keys(highlights).length,
      report: raw.length > maxChars ? JSON.parse(JSON.stringify(parsed)) : parsed,
      rawTruncated: raw.length > maxChars,
      note:
        Object.keys(highlights).length === 0
          ? "No recognizable metric keys found; inspect the full report object."
          : "metricHighlights flattens any key matching precision/recall/mrr/ndcg/latency/citation/threshold/regression."
    });
  }
);

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  // Never use console.log() in a stdio MCP server: stdout is reserved for JSON-RPC.
  console.error(error);
  process.exit(1);
});
