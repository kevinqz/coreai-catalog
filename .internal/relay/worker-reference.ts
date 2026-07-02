/**
 * Core AI Catalog — Benchmark Privacy Relay
 *
 * Cloudflare Worker that receives benchmark reports from the app,
 * coarsens device data, strips PII, signs with Ed25519, and opens
 * a GitHub PR via the bot account.
 *
 * Deploy: wrangler deploy
 * Secrets needed: wrangler secret put RELAY_PRIVATE_KEY, wrangler secret put GITHUB_APP_TOKEN
 *
 * This is reference code. The actual deployment lives in a separate
 * private repo (coreai-relay) for credential isolation.
 */

interface BenchmarkReport {
  model_id: string;
  metric: string;
  value: number;
  unit: string;
  device_model?: string;      // raw "iPhone17,1" — coarsened before publish
  os_version?: string;        // "27.0.1" → major only
  compute_unit?: string;
  precision?: string;
  higher_is_better?: boolean;
  app_version?: string;
  environment?: Record<string, unknown>;
  // Phase 3 fields (not yet used):
  device_check_jwt?: string;  // verified then stripped
  model_hash?: string;        // verified then stripped
}

interface SanitizedReport {
  id: string;
  model_id: string;
  metric: string;
  value: number;
  unit: string;
  device_class: string;
  os_major: string;
  compute_unit: string;
  precision: string;
  extraction_method: string;
  confidence: string;
  observed_date: string;
  source: string;
  device_verified: boolean;
  model_verified: boolean;
  higher_is_better: boolean;
  submission_channel: string;
  environment: Record<string, unknown>;
}

// Ed25519 signing using Web Crypto API (available in CF Workers)
async function signPayload(payload: string, privateKeyPem: string): Promise<string> {
  // Import the Ed25519 private key
  const keyData = pemToDer(privateKeyPem);
  const key = await crypto.subtle.importKey(
    'pkcs8',
    keyData,
    { name: 'Ed25519' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign(
    'Ed25519',
    key,
    new TextEncoder().encode(payload)
  );
  // Convert to hex
  return Array.from(new Uint8Array(signature))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

function pemToDer(pem: string): ArrayBuffer {
  const b64 = pem
    .replace(/-----BEGIN[^-]+-----/g, '')
    .replace(/-----END[^-]+-----/g, '')
    .replace(/\s/g, '');
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

function mapToChipClass(deviceModel: string): string {
  const mapping: Record<string, string> = {
    'iPhone17,1': 'A18 Pro',
    'iPhone17,2': 'A18 Pro',
    'iPhone17,3': 'A18',
    'iPhone17,4': 'A18',
    'iPhone16,1': 'A18 Pro',
    'iPhone16,2': 'A18 Pro',
    'iPhone16,3': 'A18',
    'iPhone15,2': 'A17 Pro',
    'iPhone15,3': 'A17 Pro',
    'iPad14,1': 'M2',
    'iPad14,2': 'M2',
    'iPad14,3': 'M2',
    'iPad14,4': 'M2',
    'iPad14,5': 'M4',
    'iPad14,6': 'M4',
    'Mac15,1': 'M3',
    'Mac15,2': 'M3',
    'Mac15,3': 'M3 Max',
    'Mac15,4': 'M3 Max',
    'Mac15,5': 'M3 Max',
    'Mac15,6': 'M3 Max',
    'Mac15,7': 'M3 Max',
    'Mac15,8': 'M3 Max',
    'Mac15,9': 'M3 Max',
    'Mac15,10': 'M3 Max',
    'Mac15,11': 'M4 Max',
    'Mac15,12': 'M4 Max',
    'Mac15,13': 'M4 Max',
    'Mac15,14': 'M4 Max',
    'Mac15,15': 'M4 Max',
    'Mac15,16': 'M4 Max',
    'Mac15,17': 'M4 Max',
    'Mac15,18': 'M4 Max',
  };
  return mapping[deviceModel] || deviceModel || 'unknown';
}

function coarsenReport(report: BenchmarkReport): SanitizedReport {
  const today = new Date().toISOString().split('T')[0]; // YYYY-MM-DD only
  const osMajor = report.os_version?.split('.')[0] || 'unknown';
  const chipClass = mapToChipClass(report.device_model || '');

  return {
    id: `bm-${crypto.randomUUID()}`,
    model_id: report.model_id,
    metric: report.metric,
    value: report.value,
    unit: report.unit,
    device_class: chipClass,           // coarsened
    os_major: osMajor,                  // major version only
    compute_unit: report.compute_unit || 'unknown',
    precision: report.precision || 'unknown',
    extraction_method: 'app_benchmark_protocol',
    confidence: 'medium',               // Phase 3 upgrades to 'high' with DeviceCheck
    observed_date: today,               // date only, no time
    source: 'crowdsourced-relay',
    device_verified: false,             // Phase 3: true when DeviceCheck verified
    model_verified: false,              // Phase 3: true when hash verified
    higher_is_better: report.higher_is_better ?? true,
    submission_channel: report.app_version || 'unknown',
    environment: report.environment || {},
    // NEVER include: device_model (raw), os_version (full), device_check_jwt, model_hash
  };
}

async function openBenchmarkPR(
  token: string,
  jsonlLine: string,
  report: SanitizedReport
): Promise<{ html_url: string }> {
  const owner = 'kevinqz';
  const repo = 'coreai-catalog';
  const branch = `benchmark/${report.id}`;

  // 1. Get main branch SHA
  const mainRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/git/refs/heads/main`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
  });
  const mainData = await mainRes.json();
  const mainSha = mainData.object.sha;

  // 2. Create branch
  await fetch(`https://api.github.com/repos/${owner}/${repo}/git/refs`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
    body: JSON.stringify({ ref: `refs/heads/${branch}`, sha: mainSha }),
  });

  // 3. Get current file SHA (for update)
  const fileRes = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/contents/benchmarks.jsonl?ref=${branch}`,
    { headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' } }
  );
  const fileData = await fileRes.json();
  const fileSha = fileData.sha;

  // 4. Append our line to the file
  const currentContent = atob(fileData.content);
  const newContent = currentContent.trimEnd() + '\n' + jsonlLine + '\n';
  const newContentB64 = btoa(newContent);

  // 5. Commit
  await fetch(`https://api.github.com/repos/${owner}/${repo}/contents/benchmarks.jsonl`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
    body: JSON.stringify({
      message: `benchmark: ${report.model_id} on ${report.device_class}`,
      content: newContentB64,
      sha: fileSha,
      branch,
    }),
  });

  // 6. Open PR
  const prTitle = `benchmark: ${report.model_id} on ${report.device_class}`;
  const prBody = `## Benchmark Submission\n\nAutomated submission from the benchmark relay.\n\n- Model: \`${report.model_id}\`\n- Device: \`${report.device_class}\`\n- Metric: \`${report.metric}\` = ${report.value} ${report.unit}\n\nThis PR adds 1 line to \`benchmarks.jsonl\`. The validation Action will run automatically.`;

  const prRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/pulls`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
    body: JSON.stringify({
      title: prTitle,
      body: prBody,
      head: branch,
      base: 'main',
    }),
  });
  const prData = await prRes.json();

  // 7. Add label
  await fetch(`https://api.github.com/repos/${owner}/${repo}/issues/${prData.number}/labels`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
    body: JSON.stringify({ labels: ['benchmark-submission'] }),
  });

  return { html_url: prData.html_url };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only accept POST
    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'Method not allowed' }), {
        status: 405,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    try {
      const report = await request.json() as BenchmarkReport;

      // Validate minimum fields
      if (!report.model_id || !report.metric || typeof report.value !== 'number') {
        return new Response(JSON.stringify({
          error: 'Missing required fields: model_id, metric, value',
        }), { status: 400, headers: { 'Content-Type': 'application/json' } });
      }

      // 1. Coarsen device data (strip PII)
      const sanitized = coarsenReport(report);

      // 2. Sign the payload
      const payloadJson = JSON.stringify(sanitized);
      const signature = await signPayload(payloadJson, env.RELAY_PRIVATE_KEY);

      // 3. Build final JSONL line with signature
      const jsonlLine = JSON.stringify({
        ...sanitized,
        _signature: signature,
      });

      // 4. Open PR via GitHub API
      const pr = await openBenchmarkPR(env.GITHUB_APP_TOKEN, jsonlLine, sanitized);

      return new Response(JSON.stringify({
        success: true,
        pr_url: pr.html_url,
        benchmark_id: sanitized.id,
      }), { status: 201, headers: { 'Content-Type': 'application/json' } });

    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      return new Response(JSON.stringify({ error: message }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }
  },
};

interface Env {
  RELAY_PRIVATE_KEY: string;     // Ed25519 PEM, set via wrangler secret
  GITHUB_APP_TOKEN: string;       // Fine-grained PAT, set via wrangler secret
}
