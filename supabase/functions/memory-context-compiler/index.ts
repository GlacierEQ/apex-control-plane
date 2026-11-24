import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPA_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const MEM0_BASE = "https://api.mem0.ai";
const MEM0_USER_ID = Deno.env.get("MEM0_USER_ID") || "operator";
const db = createClient(SUPA_URL, SERVICE_ROLE, { auth: { persistSession:false, autoRefreshToken:false } });

function safeEqual(a:string,b:string){
  const aa=new TextEncoder().encode(a), bb=new TextEncoder().encode(b);
  if(aa.length!==bb.length) return false;
  let d=0; for(let i=0;i<aa.length;i++) d|=aa[i]^bb[i];
  return d===0;
}
async function authorized(req:Request){
  const cap=req.headers.get("x-context-compiler-capability")??"";
  if(cap){
    const {data,error}=await db.rpc("consume_context_compiler_capability_v1",{p_token:cap});
    if(!error&&data===true) return true;
  }
  const t=req.headers.get("x-apex-cron-token")??"";
  if(t){
    const {data,error}=await db.rpc("verify_apex_internal_cron_token",{p_token:t});
    if(!error&&data===true) return true;
  }
  const bearer=(req.headers.get("authorization")??"").replace(/^Bearer\\s+/i,"").trim();
  return !!bearer&&safeEqual(bearer,SERVICE_ROLE);
}

async function loadRuntimeSecret(secretKey:string,purpose:string){
  const {data,error}=await db.rpc("secret_keeper_runtime_get",{
    p_secret_key:secretKey,p_purpose:purpose,p_request_id:crypto.randomUUID()
  });
  if(!error&&typeof data==="string"&&data.length>0) return data;
  return Deno.env.get(secretKey)??"";
}
async function sha256(text:string){
  const bytes=new TextEncoder().encode(text);
  const digest=await crypto.subtle.digest("SHA-256",bytes);
  return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,"0")).join("");
}
type ProviderResult={ok:boolean;status:number;data:any|null;error?:string};
async function mem0Fetch(path:string,key:string,opts:RequestInit={}):Promise<ProviderResult>{
  try{
    const response=await fetch(`${MEM0_BASE}${path}`,{
      ...opts,
      headers:{
        Authorization:`Token ${key}`,
        "Content-Type":"application/json",
        ...(opts.headers??{})
      },
      signal:AbortSignal.timeout(12000)
    });
    const text=await response.text();
    let data:any=null;
    try{data=text?JSON.parse(text):null;}catch{data=text||null;}
    return response.ok?{ok:true,status:response.status,data}:{ok:false,status:response.status,data,error:`HTTP ${response.status}`};
  }catch(error){
    return {ok:false,status:0,data:null,error:error instanceof Error?error.message:String(error)};
  }
}
function uuidLike(value:any){
  return typeof value==="string"&&/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}
function authorityRank(status:any){
  switch(String(status??"unresolved").toLowerCase()){
    case "verified":
    case "source_verified":
    case "provider_native": return 1;
    case "external_verified":
    case "operator_directive": return 2;
    case "operator_observation":
    case "firsthand": return 3;
    case "unresolved": return 5;
    case "derived": return 6;
    case "inference":
    case "assistant_derived": return 7;
    default: return 8;
  }
}
function isHighAuthority(status:any){
  return authorityRank(status)<=3;
}
function publicRecord(row:any, route:any){
  return {
    memory_id:row.id,
    content:row.content,
    case_id:row.case_id,
    memory_type:row.memory_type,
    source:row.source,
    importance_score:row.importance_score,
    authority_status:row.authority_status,
    source_id:row.source_id,
    source_uri:row.source_uri,
    source_hash:row.source_hash,
    source_type:row.source_type,
    verification_method:row.verification_method,
    observed_at:row.observed_at,
    court_facing:row.court_facing,
    contradiction_links:row.contradiction_links??[],
    supersedes:row.supersedes,
    created_at:row.created_at,
    retrieval:route
  };
}

Deno.serve(async(req:Request)=>{
  if(req.method!=="POST"){
    return new Response(JSON.stringify({error:"method_not_allowed"}),{status:405,headers:{"Content-Type":"application/json"}});
  }
  if(!(await authorized(req))){
    return new Response(JSON.stringify({error:"unauthorized"}),{status:401,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
  }

  let body:any={};
  try{body=await req.json();}catch{}
  // Quota-safe source-native bulk read. Unlike normal context compilation, this
  // mode never calls Mem0 search and never persists a duplicate context packet.
  // Exact matter/checkpoint isolation and byte budget are enforced by the RPC.
  if(body?.mode==="organized_batch"){
    const scope=typeof body.scope==="string"?body.scope:"general";
    const caseId=typeof body.case_id==="string"&&body.case_id.trim()?body.case_id.trim():null;
    const cursor=typeof body.after_id==="string"&&body.after_id.trim()?body.after_id.trim():null;
    if(cursor&&!uuidLike(cursor)){
      return new Response(JSON.stringify({error:"invalid_bulk_cursor"}),{status:400,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
    }
    const rawCount=Number(body.max_records??2048);
    const rawBytes=Number(body.max_bytes??1500000);
    if(!Number.isSafeInteger(rawCount)||rawCount<1||!Number.isSafeInteger(rawBytes)||rawBytes<65536){
      return new Response(JSON.stringify({error:"invalid_bulk_limits"}),{status:400,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
    }
    const {data,error}=await db.rpc("memory_organized_batch_v1",{
      p_scope:scope,p_case_id:caseId,p_after_id:cursor,
      p_max_records:Math.min(rawCount,5000),
      p_max_bytes:Math.min(rawBytes,2000000),
      p_include_content:body.include_content!==false,
      p_include_metadata:body.include_metadata===true
    });
    if(error){
      return new Response(JSON.stringify({error:"organized_batch_rejected",detail:error.message}),{status:400,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
    }
    return new Response(JSON.stringify(data),{status:200,headers:{"Content-Type":"application/json","Cache-Control":"no-store","X-GlacierEQ-Memory-Route":"organized-batch-v1"}});
  }

  const query=typeof body?.query==="string"?body.query.trim():"";
  if(!query){
    return new Response(JSON.stringify({error:"query_required"}),{status:400,headers:{"Content-Type":"application/json"}});
  }
  if(query.length>8000){
    return new Response(JSON.stringify({error:"query_too_large"}),{status:400,headers:{"Content-Type":"application/json"}});
  }

  const caseId=typeof body?.case_id==="string"&&body.case_id.trim()?body.case_id.trim():null;
  const mission=typeof body?.mission==="string"&&body.mission.trim()?body.mission.trim():"continuity";
  const agentId=typeof body?.agent_id==="string"&&body.agent_id.trim()?body.agent_id.trim():"runtime";
  const objective=typeof body?.objective==="string"&&body.objective.trim()?body.objective.trim():query;
  const matterKey=typeof body?.matter_key==="string"&&body.matter_key.trim()?body.matter_key.trim():caseId;
  const compilationPolicy={
    context_first:true,
    transition_semantics:"enrichment_not_permission",
    missing_context_effect:"recovery_debt_and_route_enrichment",
    mission_stop_authority:false,
    source_state_outranks_compression:true,
    operator_authority_preserved:true,
    ...(body?.compilation_policy&&typeof body.compilation_policy==="object"&&!Array.isArray(body.compilation_policy)?body.compilation_policy:{})
  };
  const userId=MEM0_USER_ID;
  const topK=Math.max(4,Math.min(Number(body?.top_k??12)||12,24));
  const threshold=Math.max(0,Math.min(Number(body?.threshold??0.1)||0.1,1));
  const compiledAt=new Date().toISOString();

  const diagnostics:any={
    mem0:{status:"not_attempted",returned:0,rehydratable:0,orphans:0},
    supabase:{status:"ok",returned:0},
    exclusions:{superseded:0,case_scope:0,missing:0}
  };

  const scoreById=new Map<string,number>();
  const mem0RefById=new Map<string,string>();
  const mem0DirectVerifiedIds=new Set<string>();
  const candidateIds=new Set<string>();

  const mem0Key=await loadRuntimeSecret("MEM0_GLACIEREQ_API_KEY","memory-context-compiler");
  if(mem0Key){
    const sr=await mem0Fetch("/v3/memories/search/",mem0Key,{
      method:"POST",
      body:JSON.stringify({
        query,
        filters:{user_id:userId},
        top_k:topK,
        threshold,
        rerank:true
      })
    });
    if(sr.ok){
      const results=Array.isArray(sr.data?.results)?sr.data.results:[];
      diagnostics.mem0.status="ok";
      diagnostics.mem0.returned=results.length;
      for(const hit of results){
        const canonicalId=hit?.metadata?.glaciereq_memory_id;
        if(uuidLike(canonicalId)){
          candidateIds.add(canonicalId);
          diagnostics.mem0.rehydratable++;
          if(typeof hit?.score==="number") scoreById.set(canonicalId,hit.score);
          if(typeof hit?.id==="string") mem0RefById.set(canonicalId,hit.id);
        }else{
          diagnostics.mem0.orphans++;
        }
      }
    }else{
      diagnostics.mem0.status="degraded";
      diagnostics.mem0.http_status=sr.status;
      diagnostics.mem0.error=sr.error??"search_failed";
    }
  }else{
    diagnostics.mem0.status="degraded";
    diagnostics.mem0.error="credential_unavailable";
  }

  const {data:lexical,error:lexError}=await db.rpc("memory_authoritative_candidates_v1",{
    p_query:query,p_case_id:caseId,p_limit:Math.max(topK*2,24)
  });
  if(lexError){
    diagnostics.supabase.status="degraded";
    diagnostics.supabase.error=lexError.message;
  }else{
    const rows=Array.isArray(lexical)?lexical:[];
    diagnostics.supabase.returned=rows.length;
    for(const x of rows){
      if(uuidLike(x?.memory_id)){
        candidateIds.add(x.memory_id);
        const prior=scoreById.get(x.memory_id)??0;
        if(typeof x?.recall_score==="number") scoreById.set(x.memory_id,Math.max(prior,x.recall_score));
      }
    }
  }

  const ids=[...candidateIds];
  let rows:any[]=[];
  if(ids.length){
    let q=db.from("apex_memories")
      .select("id,case_id,memory_type,content,source,importance_score,authority_status,source_id,source_uri,source_hash,source_type,verification_method,observed_at,court_facing,contradiction_links,supersedes,created_at,mem0_id")
      .in("id",ids);
    if(caseId) q=q.eq("case_id",caseId);
    const {data,error}=await q;
    if(error){
      return new Response(JSON.stringify({error:"authoritative_rehydrate_failed",detail:error.message}),{status:500,headers:{"Content-Type":"application/json"}});
    }
    rows=data??[];
  }

  const hydratedIds=new Set(rows.map(r=>String(r.id)));
  diagnostics.exclusions.missing=ids.filter(id=>!hydratedIds.has(id)).length;

  let supersededIds=new Set<string>();
  if(rows.length){
    const rowIds=rows.map(r=>r.id);
    const {data:newer}=await db.from("apex_memories").select("supersedes").in("supersedes",rowIds);
    supersededIds=new Set((newer??[]).map((x:any)=>String(x.supersedes)).filter(Boolean));
  }

  const ranked=rows
    .filter(r=>{
      if(supersededIds.has(String(r.id))){diagnostics.exclusions.superseded++;return false;}
      return true;
    })
    .map(r=>({
      row:r,
      score:scoreById.get(String(r.id))??0,
      mem0_id:mem0RefById.get(String(r.id))??null,
      authority_rank:authorityRank(r.authority_status)
    }))
    .sort((a,b)=>
      a.authority_rank-b.authority_rank ||
      b.score-a.score ||
      Number(b.row.importance_score??0.5)-Number(a.row.importance_score??0.5) ||
      String(b.row.created_at).localeCompare(String(a.row.created_at))
    )
    .slice(0,Math.max(topK,16));

  // The monthly Mem0 search cap must remain visible. For already-ranked, in-scope,
  // nonsuperseded Supabase memories, a small number of documented provider GETs
  // independently verifies their existing Mem0 bindings without search or writes.
  if(diagnostics.mem0.http_status===429&&mem0Key){
    const directCandidates=ranked
      .filter(x=>uuidLike(x.row.mem0_id)&&typeof x.row.content==="string")
      .slice(0,3);
    diagnostics.mem0.direct_get_attempted=directCandidates.length;
    diagnostics.mem0.direct_get_verified=0;
    diagnostics.mem0.direct_get_failed=0;
    const proofResults=await Promise.all(directCandidates.map(async(x)=>{
      const providerId=String(x.row.mem0_id);
      const response=await mem0Fetch(`/v1/memories/${encodeURIComponent(providerId)}/`,mem0Key,{method:"GET"});
      return {x,providerId,response};
    }));
    for(const {x,providerId,response} of proofResults){
      const remote=response.data??{};
      const md=remote.metadata&&typeof remote.metadata==="object"?remote.metadata:{};
      const remoteText=typeof remote.memory==="string"?remote.memory:(typeof remote.text==="string"?remote.text:"");
      if(response.ok&&String(remote.id??"")===providerId
         &&String(remote.user_id??"")===userId
         &&String(md.glaciereq_memory_id??"")===String(x.row.id)
         &&remoteText===String(x.row.content)){
        const canonicalId=String(x.row.id);
        mem0RefById.set(canonicalId,providerId);
        mem0DirectVerifiedIds.add(canonicalId);
        diagnostics.mem0.direct_get_verified++;
      }else{
        diagnostics.mem0.direct_get_failed++;
      }
    }
    diagnostics.mem0.alternate_route="bounded_verified_direct_get";
    diagnostics.mem0.search_quota_status="still_limited";
  }

  const verifiedOrHigh=ranked
    .filter(x=>isHighAuthority(x.row.authority_status))
    .map(x=>publicRecord(x.row,{score:x.score,mem0_id:mem0RefById.get(String(x.row.id))??x.mem0_id,routes:[...((mem0RefById.has(String(x.row.id))||x.mem0_id)?[mem0DirectVerifiedIds.has(String(x.row.id))?"mem0_direct_get":"mem0"]:[]),"supabase"]}));

  const unresolvedOrDerived=ranked
    .filter(x=>!isHighAuthority(x.row.authority_status))
    .map(x=>publicRecord(x.row,{score:x.score,mem0_id:mem0RefById.get(String(x.row.id))??x.mem0_id,routes:[...((mem0RefById.has(String(x.row.id))||x.mem0_id)?[mem0DirectVerifiedIds.has(String(x.row.id))?"mem0_direct_get":"mem0"]:[]),"supabase"]}));

  const context={
    schema:"glaciereq.memory.context.v3",
    compiled_at:compiledAt,
    query,
    mission,
    agent_id:agentId,
    objective,
    matter_key:matterKey,
    compilation_policy:compilationPolicy,
    scope:{user_id:userId,case_id:caseId},
    invariants:{
      mem0_is_projection:true,
      mem0_text_never_promoted_without_supabase_rehydration:true,
      unresolved_not_promoted_to_verified:true,
      superseded_records_excluded:true,
      provider_scores_are_retrieval_signals_not_truth_scores:true
    },
    verified_or_high_authority:verifiedOrHigh,
    unresolved_or_derived:unresolvedOrDerived,
    retrieval_diagnostics:diagnostics
  };

  const canonical=JSON.stringify(context);
  const snapshotHash=await sha256(canonical);
  const queryHash=await sha256(query);

  const {data:packet,error:packetError}=await db.from("memory_context_packets_v1")
    .insert({
      user_id:userId,
      case_id:caseId,
      mission,
      agent_id:agentId,
      objective,
      matter_key:matterKey,
      compilation_policy:compilationPolicy,
      query_text:query,
      query_sha256:queryHash,
      context_json:context,
      snapshot_hash:snapshotHash,
      retrieval_status:diagnostics,
      source_counts:{
        verified_or_high_authority:verifiedOrHigh.length,
        unresolved_or_derived:unresolvedOrDerived.length,
        mem0_candidates:diagnostics.mem0.returned+(diagnostics.mem0.direct_get_verified??0),
        supabase_candidates:diagnostics.supabase.returned
      },
      expires_at:new Date(Date.now()+24*60*60*1000).toISOString(),
      created_by:"memory-context-compiler-v2"
    })
    .select("packet_id,snapshot_hash,expires_at,created_at")
    .single();

  if(packetError){
    return new Response(JSON.stringify({error:"packet_persist_failed",detail:packetError.message,context}),{status:500,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
  }

  return new Response(JSON.stringify({
    packet_id:packet.packet_id,
    snapshot_hash:packet.snapshot_hash,
    expires_at:packet.expires_at,
    context
  }),{
    status:200,
    headers:{"Content-Type":"application/json","Cache-Control":"no-store"}
  });
});