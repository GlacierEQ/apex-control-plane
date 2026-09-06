import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const db = createClient(SUPABASE_URL, SERVICE_KEY);
const SLOW_MS = 1000;
const SLOW_STREAK_REQUIRED = 3;
const PROVIDER_RECEIPT_MAX_AGE_MS = 24 * 60 * 60 * 1000;
const HARD_FAILURE_CIRCUIT_THRESHOLD = 10;
const AUTH_CIRCUIT_THRESHOLD = 3;
const AUTH_REPROBE_MS = 6 * 60 * 60 * 1000;
const HARD_FAILURE_REPROBE_MS = 30 * 60 * 1000;

type Status = "HEALTHY"|"DEGRADED"|"FAILED"|"UNKNOWN"|"CONFIGURATION_REQUIRED"|"AUTH_FAILED";
type Connector = {name:string; url?:string; authEnv?:string; apiKeyHeader?:string; method?:"GET"|"POST"; body?:string; probeMode?:"http"|"provider_native_external"};
type Probe = {status:Status; latencyMs:number|null; errorMsg:string|null; healthScore:number; reason:string};
type PriorHealth = {status?:Status; consecutive_failures?:number; retry_after?:string|null; error_msg?:string|null};

const CONNECTORS: Connector[] = [
  {name:"supabase", url:`${SUPABASE_URL}/rest/v1/`},
  {name:"github", url:"https://api.github.com/octocat"},
  {name:"notion", url:"https://api.notion.com/v1/users/me", authEnv:"NOTION_API_KEY"},
  {name:"clickup", url:"https://api.clickup.com/api/v2/user", authEnv:"CLICKUP_API_KEY"},
  {name:"notion_native", probeMode:"provider_native_external"},
  {name:"clickup_native", probeMode:"provider_native_external"},
  {name:"airtable", url:"https://api.airtable.com/v0/meta/whoami", authEnv:"AIRTABLE_API_KEY"},
  {name:"motherduck", probeMode:"provider_native_external"},
  {name:"sentry", url:"https://sentry.io/api/0/", authEnv:"SENTRY_AUTH_TOKEN"},
  {name:"pinecone", url:"https://api.pinecone.io/indexes", authEnv:"PINECONE_API_KEY", apiKeyHeader:"Api-Key"},
  {name:"supermemory", url:"https://api.supermemory.ai/v3/documents/list", method:"POST", body:JSON.stringify({page:1,limit:1,includeContent:false}), authEnv:"SUPERMEMORY_API_KEY"},
  {name:"vercel", url:"https://api.vercel.com/v2/projects", authEnv:"VERCEL_TOKEN"},
];

async function secret(key:string, purpose:string){ const {data,error}=await db.rpc("secret_keeper_runtime_get",{p_secret_key:key,p_purpose:purpose,p_request_id:crypto.randomUUID()}); return error||typeof data!=="string"?"":data; }
function actionable(s:Status){return ["DEGRADED","FAILED","AUTH_FAILED","CONFIGURATION_REQUIRED"].includes(s)}
function unavailable(s:Status){return ["FAILED","AUTH_FAILED","CONFIGURATION_REQUIRED"].includes(s)}
function circuitOpen(prev:PriorHealth, nowMs:number){
  if(!prev.retry_after || !prev.status || !unavailable(prev.status)) return false;
  const retryAt=Date.parse(prev.retry_after);
  return Number.isFinite(retryAt) && retryAt>nowMs;
}
function nextRetry(status:Status, failures:number, nowMs:number){
  if((status==="AUTH_FAILED"||status==="CONFIGURATION_REQUIRED") && failures>=AUTH_CIRCUIT_THRESHOLD) return new Date(nowMs+AUTH_REPROBE_MS).toISOString();
  if(status==="FAILED" && failures>=HARD_FAILURE_CIRCUIT_THRESHOLD) return new Date(nowMs+HARD_FAILURE_REPROBE_MS).toISOString();
  return null;
}

async function providerNativeProbe(c:Connector):Promise<Probe>{
  const cutoff = new Date(Date.now() - PROVIDER_RECEIPT_MAX_AGE_MS).toISOString();
  const q = await db.from("apex_loop_health")
    .select("status,ts,metadata")
    .eq("component", c.name)
    .eq("layer", "provider_native_connector")
    .gte("ts", cutoff)
    .order("ts", {ascending:false})
    .limit(1)
    .maybeSingle();
  if(q.error || !q.data) return {status:"UNKNOWN",latencyMs:null,errorMsg:null,healthScore:100,reason:"provider_native_receipt_missing_or_stale"};
  const s = String(q.data.status) as Status;
  return {status:s,latencyMs:null,errorMsg:null,healthScore:s==="HEALTHY"?100:0,reason:"provider_native_receipt"};
}

async function httpProbe(c:Connector):Promise<Probe>{
  if(c.probeMode==="provider_native_external") return providerNativeProbe(c);
  if(!c.url) return {status:"CONFIGURATION_REQUIRED",latencyMs:null,errorMsg:"endpoint is not configured",healthScore:0,reason:"missing_endpoint"};
  const headers:Record<string,string>={"User-Agent":"CaseBrain-Runtime/3.2"};
  if(c.name==="supabase"){headers.apikey=SERVICE_KEY;headers.Authorization=`Bearer ${SERVICE_KEY}`;}
  if(c.authEnv){const k=await secret(c.authEnv,`health:${c.name}`);if(!k)return{status:"CONFIGURATION_REQUIRED",latencyMs:null,errorMsg:`${c.authEnv} is not configured`,healthScore:0,reason:"missing_secret"};headers[c.apiKeyHeader??"Authorization"]=c.apiKeyHeader?k:`Bearer ${k}`;}
  const started=performance.now();
  try{
    const r=await fetch(c.url,{method:c.method??"GET",headers,body:c.method==="POST"?(c.body??"{}"):undefined,signal:AbortSignal.timeout(8000)});
    const ms=Math.round(performance.now()-started);
    if(r.status>=200&&r.status<300)return{status:"HEALTHY",latencyMs:ms,errorMsg:null,healthScore:100,reason:"provider_probe_ok"};
    if(r.status===401||r.status===403)return{status:"AUTH_FAILED",latencyMs:ms,errorMsg:`HTTP ${r.status}`,healthScore:0,reason:"provider_auth_rejected"};
    return{status:"FAILED",latencyMs:ms,errorMsg:`HTTP ${r.status}`,healthScore:0,reason:"provider_http_failure"};
  }catch(e){return{status:"FAILED",latencyMs:Math.round(performance.now()-started),errorMsg:e instanceof Error?e.message:String(e),healthScore:0,reason:"provider_transport_failure"};}
}

async function syncIncident(name:string,status:Status,failures:number,errorMsg:string|null,now:string){
 const q=await db.from("apex_connector_incidents").select("id,retry_count").eq("connector",name).is("resolved_at",null).order("opened_at",{ascending:false}).limit(1).maybeSingle();
 const open=q.data;
 if(actionable(status)){
   if(!open) await db.from("apex_connector_incidents").insert({connector:name,incident_type:status,opened_at:now,retry_count:failures,last_error:errorMsg,notes:"canonical health runtime v3.2"});
   else if((open.retry_count??0)!==failures) await db.from("apex_connector_incidents").update({incident_type:status,retry_count:failures,last_error:errorMsg}).eq("id",open.id);
 }else if(status==="HEALTHY"&&open){await db.from("apex_connector_incidents").update({resolved_at:now,notes:`Recovered after ${open.retry_count??failures} recorded failures`}).eq("id",open.id);}
}

Deno.serve(async()=>{
 const now=new Date().toISOString(); const nowMs=Date.now(); const results:any[]=[];
 for(const c of CONNECTORS){
   const prevQ=await db.from("apex_connector_health").select("status,consecutive_failures,retry_after,error_msg").eq("connector",c.name).maybeSingle();
   const prev=(prevQ.data??{}) as PriorHealth;
   const prior=prev.consecutive_failures??0;
   let p:Probe;
   let failures=prior;
   let retryAfter:string|null=prev.retry_after??null;

   if(circuitOpen(prev,nowMs)){
     p={status:prev.status!,latencyMs:null,errorMsg:prev.error_msg??null,healthScore:0,reason:"circuit_breaker_hold"};
   }else{
     p=await httpProbe(c);
     failures=(p.status==="HEALTHY"||p.status==="UNKNOWN")?0:actionable(p.status)?prior+1:0;
     if(c.name==="supabase"&&p.status==="HEALTHY"&&p.latencyMs!==null&&p.latencyMs>=SLOW_MS){const streak=prior+1; failures=streak; p=streak>=SLOW_STREAK_REQUIRED?{...p,status:"DEGRADED",healthScore:50,reason:"latency_sustained"}:{...p,status:"HEALTHY",healthScore:90,reason:"latency_spike_not_sustained"};}
     if(c.name==="supabase"&&p.status==="HEALTHY"&&p.latencyMs!==null&&p.latencyMs<SLOW_MS) failures=0;
     retryAfter=nextRetry(p.status,failures,nowMs);
   }

   await db.from("apex_connector_health").upsert({connector:c.name,last_ping:now,checked_at:now,status:p.status,latency_ms:p.latencyMs,error_msg:p.errorMsg,prev_status:prev.status??null,consecutive_failures:failures,retry_after:retryAfter},{onConflict:"connector"});
   await db.from("apex_connector_status").upsert({service:c.name,last_healthy:p.status==="HEALTHY"||p.status==="DEGRADED"?now:null,last_failed:unavailable(p.status)?now:null,consecutive_failures:failures,health_score:p.healthScore,notes:p.reason,updated_at:now},{onConflict:"service"});
   await db.from("apex_loop_health").insert({component:c.name,layer:"connector_runtime",status:p.status,latency_ms:p.latencyMs,error_message:p.errorMsg,ts:now,target_service:c.url??"provider-native connector",operator:"connector_health_ping",metadata:{writer:"connector-health-ping-v3.2",reason:p.reason,retry_after:retryAfter,circuit_open:p.reason==="circuit_breaker_hold"}});
   await syncIncident(c.name,p.status,failures,p.errorMsg,now);
   results.push({connector:c.name,failures,retryAfter,...p});
 }
 const bad=results.some(r=>unavailable(r.status));
 await db.from("apex_ops_log").insert({action:"connector_health_ping_v3_2",status:bad?"partial":"ok",details:JSON.stringify({checked:results.length,results,ts:now}),created_at:now});
 return new Response(JSON.stringify({ok:true,writer:"connector-health-ping-v3.2",checkedAt:now,results}),{headers:{"Content-Type":"application/json"}});
});
