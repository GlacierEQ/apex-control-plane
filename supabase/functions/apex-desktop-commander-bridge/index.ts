import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const admin = createClient(SUPABASE_URL, SERVICE_ROLE, {
  auth: { persistSession: false, autoRefreshToken: false },
});

type Json = Record<string, any>;

function respond(status:number, body:Json) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {"content-type":"application/json","cache-control":"no-store"},
  });
}
function obj(v:unknown):Json {
  return v && typeof v==="object" && !Array.isArray(v) ? v as Json : {};
}
function text(v:unknown, name:string, max=512, required=true):string {
  if (v===undefined || v===null || v==="") {
    if (required) throw new BridgeError(400, "missing_"+name);
    return "";
  }
  if (typeof v!=="string") throw new BridgeError(400, "invalid_"+name);
  const s=v.trim();
  if (!s && required) throw new BridgeError(400, "missing_"+name);
  if (s.length>max) throw new BridgeError(400, "invalid_"+name);
  return s;
}
class BridgeError extends Error {
  status:number; code:string; detail:Json;
  constructor(status:number, code:string, detail:Json={}) {
    super(code); this.status=status; this.code=code; this.detail=detail;
  }
}
function b64ToBytes(s:string):Uint8Array {
  const bin=atob(s.replace(/\s+/g,""));
  const out=new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++) out[i]=bin.charCodeAt(i);
  return out;
}
function bytesToHex(bytes:Uint8Array):string {
  return Array.from(bytes).map(b=>b.toString(16).padStart(2,"0")).join("");
}
async function sha256Hex(s:string):Promise<string> {
  return bytesToHex(new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(s))));
}
async function sha256BytesHex(bytes:Uint8Array):Promise<string> {
  return bytesToHex(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)));
}
async function verifyDeviceSignature(req:Request, rawBody:string, deviceId:string) {
  const timestamp=text(req.headers.get("x-glacier-timestamp"),"timestamp",32);
  const nonce=text(req.headers.get("x-glacier-nonce"),"nonce",128);
  const signatureB64=text(req.headers.get("x-glacier-signature"),"signature",512);
  const ts=Number(timestamp);
  if (!Number.isFinite(ts)) throw new BridgeError(401,"invalid_signature_timestamp");
  const now=Math.floor(Date.now()/1000);
  if (Math.abs(now-ts)>120) throw new BridgeError(401,"signature_timestamp_out_of_window");

  const {data:device,error}=await admin
    .from("desktop_commander_devices_v1")
    .select("device_id,status,public_key_spki_base64,public_key_sha256,approved_roots,capabilities,device_key,metadata")
    .eq("device_id",deviceId)
    .maybeSingle();
  if(error || !device) throw new BridgeError(401,"unknown_device");

  const path=new URL(req.url).pathname;
  const bodyHash=await sha256Hex(rawBody);
  const canonical=[timestamp,nonce,req.method.toUpperCase(),path,bodyHash].join("\n");
  let key:CryptoKey;
  try {
    key=await crypto.subtle.importKey(
      "spki",
      b64ToBytes(String(device.public_key_spki_base64)),
      {name:"Ed25519"},
      false,
      ["verify"]
    );
  } catch {
    throw new BridgeError(401,"device_public_key_invalid");
  }
  let ok=false;
  try {
    ok=await crypto.subtle.verify(
      {name:"Ed25519"},
      key,
      b64ToBytes(signatureB64),
      new TextEncoder().encode(canonical)
    );
  } catch {}
  if(!ok) throw new BridgeError(401,"device_signature_invalid");

  const {error:nonceError}=await admin
    .from("desktop_commander_nonces_v1")
    .insert({device_id:deviceId,nonce});
  if(nonceError){
    if(nonceError.code==="23505") throw new BridgeError(409,"nonce_replay_rejected");
    throw new BridgeError(500,"nonce_persistence_failed");
  }

  await admin.from("desktop_commander_nonces_v1")
    .delete()
    .eq("device_id",deviceId)
    .lt("used_at",new Date(Date.now()-10*60*1000).toISOString());

  return device as Json;
}

async function recordHeartbeat(device:Json, input:Json) {
  const capabilities=Array.isArray(input.capabilities)
    ? input.capabilities.slice(0,128)
    : device.capabilities || [];
  const {data,error}=await admin.rpc("record_desktop_commander_heartbeat_v1",{
    p_device_id:device.device_id,
    p_agent_version:typeof input.agent_version==="string" ? input.agent_version.slice(0,64) : null,
    p_capabilities:capabilities,
    p_metadata:obj(input.metadata),
  });
  if(error) throw new BridgeError(500,"heartbeat_persistence_failed",{message:error.message});
  return data;
}

Deno.serve(async (req:Request) => {
  const correlationId=crypto.randomUUID();
  if(req.method!=="POST") return respond(405,{ok:false,error:"method_not_allowed",correlation_id:correlationId});
  const raw=await req.text();
  if(raw.length>256*1024) return respond(413,{ok:false,error:"request_too_large",correlation_id:correlationId});
  let input:Json={};
  try { input=obj(JSON.parse(raw||"{}")); }
  catch { return respond(400,{ok:false,error:"invalid_json",correlation_id:correlationId}); }

  try {
    const action=text(input.action,"action",64);
    if(action==="enroll"){
      const tokenHeader=req.headers.get("x-glacier-enrollment-token");
      if(!tokenHeader) throw new BridgeError(401,"enrollment_token_required");
      const token=text(tokenHeader,"enrollment_token",256);
      const {data:valid,error:validateError}=await admin.rpc(
        "validate_desktop_commander_enrollment_token_v1",
        {p_candidate:token}
      );
      if(validateError || valid!==true) throw new BridgeError(401,"enrollment_token_invalid");

      const publicKey=text(input.public_key_spki_base64,"public_key_spki_base64",4096);
      const publicKeyHash=await sha256BytesHex(b64ToBytes(publicKey));
      const suppliedHash=text(input.public_key_sha256,"public_key_sha256",64);
      if(publicKeyHash!==suppliedHash) throw new BridgeError(400,"public_key_hash_mismatch");

      const {data,error}=await admin.rpc("register_desktop_commander_device_v1",{
        p_device_key:text(input.device_key,"device_key",128),
        p_public_key_spki_base64:publicKey,
        p_public_key_sha256:suppliedHash,
        p_host_fingerprint_sha256:text(input.host_fingerprint_sha256,"host_fingerprint_sha256",64),
        p_platform:text(input.platform,"platform",64),
        p_hostname_hash:text(input.hostname_hash,"hostname_hash",128,false)||null,
        p_agent_version:text(input.agent_version,"agent_version",64,false)||null,
        p_capabilities:Array.isArray(input.capabilities)?input.capabilities:[],
        p_requested_roots:Array.isArray(input.requested_roots)?input.requested_roots:[],
        p_metadata:obj(input.metadata),
      });
      if(error) throw new BridgeError(500,"device_enrollment_failed",{message:error.message});
      return respond(202,{ok:true,correlation_id:correlationId,enrollment:data});
    }

    const deviceIdHeader=req.headers.get("x-glacier-device-id");
    if(!deviceIdHeader) throw new BridgeError(401,"device_id_required");
    const deviceId=text(deviceIdHeader,"device_id",64);
    const device=await verifyDeviceSignature(req,raw,deviceId);

    if(action==="status"){
      return respond(200,{ok:true,correlation_id:correlationId,device:{
        device_id:device.device_id,
        device_key:device.device_key,
        status:device.status,
        approved_roots:device.approved_roots,
        capabilities:device.capabilities,
      }});
    }
    if(action==="heartbeat"){
      const heartbeat=await recordHeartbeat(device,input);
      return respond(200,{ok:true,correlation_id:correlationId,heartbeat});
    }
    if(action==="claim"){
      if(device.status!=="approved") throw new BridgeError(403,"device_not_approved");
      const limit=Math.max(1,Math.min(Number(input.limit||4),16));
      const {data,error}=await admin.rpc("claim_desktop_commander_jobs_v1",{
        p_device_id:device.device_id,p_limit:limit,p_lease_seconds:120
      });
      if(error) throw new BridgeError(500,"job_claim_failed",{message:error.message});
      const jobs=Array.isArray(data)?data:[];
      return respond(200,{ok:true,correlation_id:correlationId,jobs});
    }
    if(action==="finish"){
      if(device.status!=="approved") throw new BridgeError(403,"device_not_approved");
      const {data,error}=await admin.rpc("finish_desktop_commander_job_v1",{
        p_job_id:text(input.job_id,"job_id",64),
        p_device_id:device.device_id,
        p_status:text(input.status,"status",16),
        p_result_summary:obj(input.result_summary),
        p_result_hash:text(input.result_hash,"result_hash",128,false)||null,
        p_error_code:text(input.error_code,"error_code",128,false)||null,
        p_error_detail:obj(input.error_detail),
        p_duration_ms:Number.isFinite(Number(input.duration_ms)) ? Number(input.duration_ms) : null,
      });
      if(error) throw new BridgeError(500,"job_finish_failed",{message:error.message});
      return respond(200,{ok:true,correlation_id:correlationId,result:data});
    }
    throw new BridgeError(400,"unsupported_action");
  } catch(e) {
    const be=e instanceof BridgeError ? e : new BridgeError(500,"internal_bridge_error");
    return respond(be.status,{ok:false,error:be.code,detail:be.detail,correlation_id:correlationId});
  }
});