import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");

const admin = createClient(SUPABASE_URL, SERVICE_ROLE, { auth: { persistSession: false, autoRefreshToken: false } });
const ROUTER_URL = SUPABASE_URL + "/functions/v1/apex-github-router";
const BULK_CONNECTOR_URL = SUPABASE_URL + "/functions/v1/apex-github-connector";
const WORKER_URL = SUPABASE_URL + "/functions/v1/apex-github-batch-worker";
const WORKER_ID = "github-edge-batch-v2";
const WORKER_VERSION = 6;
const HARD_RUNTIME_MS = 48000;
const RETRYABLE = new Set([429, 500, 502, 503, 504]);
const SAFE_RETRY_ERRORS = new Set(["resource_lease_busy","circuit_open","gateway_transport_failure","preflight_read_failed","edge_function_rate_limited"]);

type Json = Record<string, unknown>;
type Item = {
  item_id:string; batch_id:string; request_id:string; operation:string; repository:string;
  arguments:Json; full_fidelity:boolean; expected_before_sha:string|null; expected_before_sha_present:boolean;
  status:string; attempts:number; max_attempts:number; execution_lane:string;
};
type Batch = {
  batch_id:string; max_concurrency:number; target_rps:number; claim_size:number;
  quality_policy:Json; status:string;
};

const HEADERS = {
  "content-type":"application/json; charset=utf-8",
  "cache-control":"no-store,max-age=0",
  "x-content-type-options":"nosniff",
};

function obj(v:unknown):Json {
  return v && typeof v === "object" && !Array.isArray(v) ? v as Json : {};
}
function reply(status:number, body:unknown) {
  return new Response(JSON.stringify(body), {status, headers:HEADERS});
}
function isWrite(op:string):boolean {
  return ["branch.create","contents.put","issue.create","issue.comment","pull.comment","workflow.dispatch"].includes(op);
}
function deterministicWrite(op:string):boolean {
  return ["branch.create","contents.put","issue.create","issue.comment","pull.comment"].includes(op);
}
function sleep(ms:number) { return new Promise((r)=>setTimeout(r,ms)); }

async function routerCall(item:Item):Promise<{ok:boolean;status:number;body:Json;durationMs:number}> {
  const started = Date.now();
  const payload:Json = {
    operation:item.operation,
    repository:item.repository,
    args:item.arguments || {},
    request_id:item.request_id,
    actor:"github-batch-worker-v2",
    full_fidelity:item.full_fidelity === true,
  };
  if (item.expected_before_sha_present) payload.expected_before_sha = item.expected_before_sha;

  try {
    const res = await fetch(ROUTER_URL, {
      method:"POST",
      signal:AbortSignal.timeout(40000),
      headers:{
        authorization:`Bearer ${SERVICE_ROLE}`,
        apikey:SERVICE_ROLE,
        "content-type":"application/json",
        accept:"application/json",
        "user-agent":`APEX-GitHub-Batch-Worker/${WORKER_VERSION}`,
        "x-region":"us-east-1",
      },
      body:JSON.stringify(payload),
    });
    const raw = await res.text();
    let body:Json = {};
    try { body = obj(JSON.parse(raw || "{}")); } catch { body = {error:"invalid_router_response"}; }
    return {ok:res.ok,status:res.status,body,durationMs:Date.now()-started};
  } catch (e) {
    if (e instanceof Deno.errors.RateLimitError) {
      return {
        ok:false,status:429,durationMs:Date.now()-started,
        body:{error:"edge_function_rate_limited",retry_after_ms:e.retryAfterMs || null}
      };
    }
    return {
      ok:false,status:503,durationMs:Date.now()-started,
      body:{error:"router_transport_failure",message:e instanceof Error ? e.message : "transport_failure"}
    };
  }
}


async function bulkReadCallV6(items:Item[]):Promise<{ok:boolean;status:number;body:Json;durationMs:number}> {
  const started=Date.now();
  const parentRequestId="batch-bulk:"+crypto.randomUUID();
  try {
    const response=await fetch(BULK_CONNECTOR_URL,{
      method:"POST",
      signal:AbortSignal.timeout(120000),
      headers:{
        authorization:`Bearer ${SERVICE_ROLE}`,
        apikey:SERVICE_ROLE,
        "content-type":"application/json",
        accept:"application/json",
        "user-agent":`APEX-GitHub-Batch-Worker/${WORKER_VERSION}`,
        "x-region":"us-east-1",
      },
      body:JSON.stringify({
        operation:"bulk.read",
        request_id:parentRequestId,
        actor:"github-batch-worker-v6",
        items:items.map((item)=>({
          request_id:item.request_id,
          operation:item.operation,
          repository:item.repository,
          args:item.arguments||{},
        }))
      })
    });
    const raw=await response.text();
    let body:Json={};
    try { body=obj(JSON.parse(raw||"{}")); } catch { body={error:"invalid_bulk_connector_response"}; }
    return {ok:response.ok,status:response.status,body,durationMs:Date.now()-started};
  } catch(e) {
    if(e instanceof Deno.errors.RateLimitError){
      return {ok:false,status:429,durationMs:Date.now()-started,body:{error:"edge_function_rate_limited",retry_after_ms:e.retryAfterMs||null}};
    }
    return {ok:false,status:503,durationMs:Date.now()-started,body:{error:"bulk_connector_transport_failure",message:e instanceof Error?e.message:"transport_failure"}};
  }
}

function classify(item:Item, call:{ok:boolean;status:number;body:Json;durationMs:number}) {
  const gateway = obj(call.body.gateway);
  const error = String(call.body.error || gateway.error || "");
  const write = isWrite(item.operation);

  if (call.ok) {
    let qualityStatus = "passed";
    const detail:Json = {
      deterministic_write: deterministicWrite(item.operation),
      gateway_readback_verified: gateway.readback_verified === true,
      response_status: call.status,
    };
    if (deterministicWrite(item.operation) && gateway.readback_verified !== true) {
      qualityStatus = "failed";
      detail.reason = "deterministic_write_missing_readback";
    } else if (item.operation === "workflow.dispatch") {
      qualityStatus = "warning";
      detail.reason = "dispatch_acceptance_not_completion";
    }
    return {status:"succeeded",outcome:"succeeded",errorCode:null,qualityStatus,qualityDetail:detail,retryAfter:null};
  }

  if (error === "fallback_required") {
    return {
      status:"blocked",outcome:"fallback_required",errorCode:"fallback_required",qualityStatus:"not_applicable",
      qualityDetail:{selected_connector:obj(call.body.plan).selected_connector || null,selected_tool:obj(call.body.plan).selected_tool || null},
      retryAfter:null
    };
  }

  if (error === "stale_write_precondition" || call.status === 428) {
    return {
      status:"failed",outcome:"rejected",errorCode:error || "write_precondition_required",qualityStatus:"failed",
      qualityDetail:{reason:error || "write_precondition_required"},retryAfter:null
    };
  }

  const ambiguous = error.includes("receipt_persistence_failed_after") ||
    error.includes("ambiguous_external_outcome") ||
    call.body.external_outcome_verified_by_gateway === true;

  if (ambiguous) {
    return {
      status:"failed",outcome:"ambiguous_external_outcome",errorCode:"ambiguous_external_outcome",
      qualityStatus:"failed",qualityDetail:{reason:"external_side_effect_may_have_occurred"},retryAfter:null
    };
  }

  const canRetry = item.attempts < item.max_attempts &&
    (!write && RETRYABLE.has(call.status) || SAFE_RETRY_ERRORS.has(error));

  if (canRetry) {
    const advised = Math.ceil(Number(call.body.retry_after_ms || 0) / 1000);
    const backoff = Math.min(900, Math.max(advised || 0, 5, 5 * Math.pow(2, Math.max(0,item.attempts-1))));
    return {
      status:"retry",outcome:"retry_scheduled",errorCode:error || `http_${call.status}`,
      qualityStatus:"pending",qualityDetail:{retryable_status:call.status},retryAfter:backoff
    };
  }

  return {
    status:"failed",outcome:"failed",errorCode:error || `http_${call.status}`,
    qualityStatus:"failed",qualityDetail:{response_status:call.status},retryAfter:null
  };
}

async function finishItem(item:Item, call:{ok:boolean;status:number;body:Json;durationMs:number}) {
  const c = classify(item,call);
  const gateway = obj(call.body.gateway);
  const plan = obj(call.body.plan);
  const summary:Json = {
    router_request_id:call.body.request_id || null,
    router_correlation_id:call.body.correlation_id || null,
    selected_connector:plan.selected_connector || null,
    selected_tool:plan.selected_tool || null,
    gateway_github_request_id:gateway.github_request_id || null,
    gateway_readback_verified:gateway.readback_verified === true,
    response_error:call.ok ? null : call.body.error || gateway.error || null,
  };

  const {error} = await admin.rpc("finish_github_batch_item_v2", {
    p_item_id:item.item_id,
    p_worker_id:WORKER_ID,
    p_status:c.status,
    p_response_status:call.status,
    p_outcome:c.outcome,
    p_result_summary:summary,
    p_error_code:c.errorCode,
    p_quality_status:c.qualityStatus,
    p_quality_detail:c.qualityDetail,
    p_duration_ms:call.durationMs,
    p_retry_after_seconds:c.retryAfter,
  });
  if (error) throw new Error("finish_item_failed:"+error.message);
  return c;
}

async function processClaim(items:Item[], batch:Batch) {
  const report:Json[]=[];
  const readItems=items.filter((item)=>!isWrite(item.operation));
  const writeItems=items.filter((item)=>isWrite(item.operation));

  if(readItems.length){
    const bulk=await bulkReadCallV6(readItems);
    const bulkResult=obj(bulk.body.result);
    const rows=Array.isArray(bulkResult.results) ? bulkResult.results as Json[] : [];

    if(bulk.ok && rows.length===readItems.length){
      const byRequest=new Map(rows.map((row)=>[String(row.request_id||""),row]));
      for(const item of readItems){
        const row=byRequest.get(item.request_id) || {};
        const ok=row.ok===true;
        const synthetic={
          ok,
          status:ok?200:Number(row.status||500),
          durationMs:Math.max(0,Math.round(bulk.durationMs/Math.max(1,readItems.length))),
          body:{
            request_id:item.request_id,
            correlation_id:row.correlation_id||null,
            plan:{selected_connector:"github.backend_ops",selected_tool:item.operation,execution_mode:"in_process_bulk_read_v3"},
            gateway:{
              github_request_id:row.github_request_id||null,
              readback_verified:row.readback_verified===true,
              error:ok?null:row.error||null
            },
            error:ok?null:row.error||"bulk_item_failed"
          } as Json
        };
        const classification=await finishItem(item,synthetic);
        report.push({
          item_id:item.item_id,operation:item.operation,repository:item.repository,
          status:classification.status,response_status:synthetic.status,
          duration_ms:synthetic.durationMs,quality_status:classification.qualityStatus,
          execution_mode:"in_process_bulk_read_v3"
        });
      }
    } else {
      for(const item of readItems){
        const synthetic={
          ok:false,status:bulk.status,durationMs:bulk.durationMs,
          body:{
            error:String(bulk.body.error||"bulk_connector_failed"),
            retry_after_ms:bulk.body.retry_after_ms||null
          } as Json
        };
        const classification=await finishItem(item,synthetic);
        report.push({
          item_id:item.item_id,operation:item.operation,repository:item.repository,
          status:classification.status,response_status:bulk.status,
          duration_ms:bulk.durationMs,quality_status:classification.qualityStatus,
          execution_mode:"bulk_connector_failure"
        });
      }
    }
  }

  if(writeItems.length){
    let nextStart=Date.now();
    const maxAttempt=Math.max(...writeItems.map((i)=>Number(i.attempts||1)));
    const retryDivisor=Math.pow(2,Math.max(0,maxAttempt-1));
    const adaptiveConcurrency=Math.max(1,Math.min(4,Math.floor(Number(batch.max_concurrency||4)/retryDivisor)));
    const adaptiveRps=Math.max(1,Math.min(4,Number(batch.target_rps||4)/retryDivisor));
    const interval=Math.max(0,Math.floor(1000/adaptiveRps));
    let index=0;

    async function pace(){
      const slot=Math.max(Date.now(),nextStart);
      nextStart=slot+interval;
      const wait=slot-Date.now();
      if(wait>0) await sleep(wait);
    }
    async function runner(){
      while(true){
        const my=index++;
        if(my>=writeItems.length) return;
        const item=writeItems[my];
        await pace();
        const call=await routerCall(item);
        const classification=await finishItem(item,call);
        report.push({
          item_id:item.item_id,operation:item.operation,repository:item.repository,
          status:classification.status,response_status:call.status,duration_ms:call.durationMs,
          quality_status:classification.qualityStatus,execution_mode:"router_write_v2"
        });
      }
    }
    await Promise.all(Array.from({length:Math.min(adaptiveConcurrency,writeItems.length)},()=>runner()));
  }

  report.push({
    _batch_worker_window:true,
    claimed:items.length,
    bulk_reads:readItems.length,
    routed_writes:writeItems.length
  });
  return report;
}

async function heartbeat(status:string) {
  await admin.rpc("heartbeat_github_batch_worker_v2", {
    p_worker_id:WORKER_ID,p_worker_type:"edge",p_connector_key:"github.backend_ops",
    p_status:status,p_max_concurrency:12,
    p_capabilities:[
      "batch.claim","batch.parallel","batch.rate_limit","batch.qc",
      "repo.get","contents.get","tree.list","branches.list","commits.list","code.search",
      "issues.list","issue.get","pulls.list","pull.get","actions.runs",
      "branch.create","contents.put","issue.create","issue.comment","pull.comment","workflow.dispatch"
    ],
    p_metadata:{worker_version:WORKER_VERSION,runtime:"supabase_edge"}
  });
}

async function pendingBackendItems():Promise<number> {
  const {count,error} = await admin.from("github_batch_items_v2")
    .select("item_id",{count:"exact",head:true})
    .eq("execution_lane","backend_ops")
    .in("status",["pending","retry"]);
  if (error) return 0;
  return count || 0;
}

Deno.serve(async (req:Request) => {
  if (req.method !== "POST") return reply(405,{ok:false,error:"method_not_allowed"});
  let input:Json = {};
  try { const raw=await req.text(); input=raw?obj(JSON.parse(raw)):{}; }
  catch { return reply(400,{ok:false,error:"invalid_json"}); }

  const maxCycles = Math.max(1,Math.min(Number(input.max_cycles || 4),8));
  const requestLimit = Math.max(1,Math.min(Number(input.limit || 100),100));
  const started = Date.now();
  const batches = new Set<string>();
  const reports:Json[] = [];
  const invocationId = WORKER_ID + ":" + crypto.randomUUID();

  const {data:dispatchLease,error:dispatchLeaseError} = await admin.rpc("acquire_github_batch_dispatch_lease_v2", {
    p_lease_key:"backend_ops",
    p_lease_owner:invocationId,
    p_ttl_seconds:55,
    p_metadata:{worker_version:WORKER_VERSION}
  });
  if (dispatchLeaseError) return reply(500,{ok:false,error:"dispatch_lease_failed",detail:dispatchLeaseError.message});
  if (obj(dispatchLease).acquired !== true) {
    return reply(200,{
      ok:true,worker_id:WORKER_ID,worker_version:WORKER_VERSION,busy:true,
      active_dispatch_owner:obj(dispatchLease).lease_owner || null,
      lease_expires_at:obj(dispatchLease).lease_expires_at || null
    });
  }

  try {
    await heartbeat("online");

    for (let cycle=0;cycle<maxCycles && Date.now()-started < HARD_RUNTIME_MS;cycle++) {
      const claimLimit = Math.min(requestLimit,32);
      const {data,error} = await admin.rpc("claim_github_batch_items_v2", {
        p_worker_id:WORKER_ID,p_execution_lane:"backend_ops",p_limit:claimLimit,p_lease_seconds:120
      });
      if (error) throw new Error("batch_claim_failed:"+error.message);
      const items = (data || []) as Item[];
      if (!items.length) break;

      const batchId = items[0].batch_id;
      batches.add(batchId);
      const {data:batchData,error:batchError} = await admin.from("github_batch_runs_v2")
        .select("batch_id,max_concurrency,target_rps,claim_size,quality_policy,status")
        .eq("batch_id",batchId).single();
      if (batchError) throw new Error("batch_read_failed:"+batchError.message);

      const batch = batchData as Batch;
      reports.push(...await processClaim(items,batch));
      await admin.rpc("finalize_github_batch_v2",{p_batch_id:batchId});
    }

    for (const id of batches) await admin.rpc("finalize_github_batch_v2",{p_batch_id:id});

    const pending = await pendingBackendItems();
    await admin.rpc("release_github_batch_dispatch_lease_v2",{
      p_lease_key:"backend_ops",p_lease_owner:invocationId,
      p_metadata:{completed:true,pending_backend_items:pending}
    });

    if (pending > 0 && typeof EdgeRuntime !== "undefined") {
      EdgeRuntime.waitUntil((async()=>{
        await sleep(750);
        try {
          await fetch(WORKER_URL,{
            method:"POST",signal:AbortSignal.timeout(60000),
            headers:{authorization:`Bearer ${SERVICE_ROLE}`,apikey:SERVICE_ROLE,"content-type":"application/json","x-region":"us-east-1"},
            body:JSON.stringify({limit:requestLimit,max_cycles:maxCycles})
          });
        } catch {}
      })());
    }

    return reply(200,{
      ok:true,worker_id:WORKER_ID,worker_version:WORKER_VERSION,
      invocation_id:invocationId,processed:reports.length,batches:[...batches],
      pending_backend_items:pending,elapsed_ms:Date.now()-started,results:reports.slice(0,100)
    });
  } catch (e) {
    await admin.rpc("release_github_batch_dispatch_lease_v2",{
      p_lease_key:"backend_ops",p_lease_owner:invocationId,
      p_metadata:{failed:true,error:e instanceof Error?e.message:"batch_worker_failure"}
    }).catch(()=>{});
    await heartbeat("online").catch(()=>{});
    return reply(500,{ok:false,error:"batch_worker_failure",message:e instanceof Error?e.message:"batch_worker_failure"});
  }
});