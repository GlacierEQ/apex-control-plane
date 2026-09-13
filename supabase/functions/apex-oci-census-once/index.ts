import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const H={"content-type":"application/json","cache-control":"no-store, max-age=0","x-content-type-options":"nosniff"};
const enc=new TextEncoder();
function json(s:number,b:unknown){return new Response(JSON.stringify(b),{status:s,headers:H});}
function b64(bytes:Uint8Array){let x="";for(let i=0;i<bytes.length;i+=0x8000)x+=String.fromCharCode(...bytes.subarray(i,i+0x8000));return btoa(x);}
function b64d(s:string){const x=atob(s);return Uint8Array.from(x,c=>c.charCodeAt(0));}
function pemDer(pem:string){const s=pem.trim().replace("-----BEGIN PRIVATE KEY-----","").replace("-----END PRIVATE KEY-----","").replace(/\s+/g,"");const b=b64d(s);return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);}
async function digestB64(text:string){return b64(new Uint8Array(await crypto.subtle.digest("SHA-256",enc.encode(text))));}
async function importKey(pem:string){return await crypto.subtle.importKey("pkcs8",pemDer(pem),{name:"RSASSA-PKCS1-v1_5",hash:"SHA-256"},false,["sign"]);}
async function sign(key:CryptoKey,method:string,host:string,path:string,date:string,body?:string){
  if(body!==undefined){const hash=await digestB64(body);const len=enc.encode(body).byteLength;const names="(request-target) host date x-content-sha256 content-type content-length";const s=`(request-target): ${method.toLowerCase()} ${path}\nhost: ${host}\ndate: ${date}\nx-content-sha256: ${hash}\ncontent-type: application/json\ncontent-length: ${len}`;const sig=b64(new Uint8Array(await crypto.subtle.sign({name:"RSASSA-PKCS1-v1_5"},key,enc.encode(s))));return {names,sig,hash,len};}
  const names="(request-target) host date";const s=`(request-target): ${method.toLowerCase()} ${path}\nhost: ${host}\ndate: ${date}`;const sig=b64(new Uint8Array(await crypto.subtle.sign({name:"RSASSA-PKCS1-v1_5"},key,enc.encode(s))));return {names,sig,hash:null,len:0};
}
async function call(creds:any,service:string,method:string,path:string,body?:unknown){
  const host=`${service}.${creds.region}.oci.oraclecloud.com`;const date=new Date().toUTCString();const key=await importKey(creds.private_key_pem);const bodyText=body===undefined?undefined:JSON.stringify(body);const sg=await sign(key,method,host,path,date,bodyText);const auth=`Signature version="1",keyId="${creds.tenancy_ocid}/${creds.user_ocid}/${creds.fingerprint}",algorithm="rsa-sha256",headers="${sg.names}",signature="${sg.sig}"`;
  const headers:Record<string,string>={date,authorization:auth,accept:"application/json"};if(bodyText!==undefined){headers["x-content-sha256"]=String(sg.hash);headers["content-type"]="application/json";headers["content-length"]=String(sg.len);}
  const r=await fetch(`https://${host}${path}`,{method,headers,body:bodyText,signal:AbortSignal.timeout(20000)});const t=await r.text();let p:any=null;try{p=t?JSON.parse(t):null}catch{p={body_length:t.length}};return {ok:r.ok,status:r.status,payload:p};
}
Deno.serve(async(req:Request)=>{
  if(req.method!=="POST")return json(405,{error:"method_not_allowed"});
  const url=Deno.env.get("SUPABASE_URL"),sr=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");if(!url||!sr)return json(500,{error:"configuration_missing"});
  const admin=createClient(url,sr,{auth:{persistSession:false,autoRefreshToken:false}});
  const gate=await admin.rpc("claim_apex_oci_census_gate");if(gate.error||gate.data?.ok!==true)return json(401,{error:gate.error?.message||gate.data?.error||"census_gate_rejected"});
  try{
    const meta=await admin.from("apex_keymaster_secrets").select("secret_ref,verification_status,status").eq("provider","oracle").eq("status","active").eq("verification_status","verified").order("created_at",{ascending:false}).limit(1).maybeSingle();
    if(meta.error||!meta.data?.secret_ref)throw new Error("verified_oracle_secret_missing");
    const ref=meta.data.secret_ref as string;
    const resolved=await admin.rpc("resolve_apex_keymaster_secret_for_broker",{p_secret_ref:ref,p_provider:"oracle",p_request_id:`oci-census-${Date.now()}`,p_actor:"apex-oci-census-once",p_operation:"read_only_resource_census"});
    if(resolved.error||typeof resolved.data?.secret!=="string")throw new Error(resolved.error?.message||"oracle_secret_resolution_failed");
    let secret=resolved.data.secret as string;const creds=JSON.parse(secret);secret="";
    const compPath=`/20160918/compartments?compartmentId=${encodeURIComponent(creds.tenancy_ocid)}&compartmentIdInSubtree=true&accessLevel=ANY&limit=1000`;
    const compartments=await call(creds,"identity","GET",compPath);
    const searchBody={type:"Structured",query:"query all resources",matchingContextType:"NONE"};
    const search=await call(creds,"query","POST","/20180409/resources?limit=1000",searchBody);
    const items=Array.isArray(search.payload?.items)?search.payload.items:[];
    const counts:Record<string,number>={};for(const item of items){const type=String(item?.resourceType||"Unknown");counts[type]=(counts[type]||0)+1;}
    const relevant=items.filter((x:any)=>/instance|vcn|subnet|volume|cluster|container/i.test(String(x?.resourceType||""))).slice(0,500);
    const snapshot=crypto.randomUUID();
    if(relevant.length){const rows=relevant.map((x:any)=>({snapshot_id:snapshot,resource_type:String(x.resourceType||"Unknown"),identifier:String(x.identifier||""),compartment_id:x.compartmentId||null,display_name:x.displayName||null,lifecycle_state:x.lifecycleState||null,availability_domain:x.availabilityDomain||null,region:creds.region,raw_summary:{timeCreated:x.timeCreated||null,freeformTags:x.freeformTags||{},definedTags:x.definedTags||{}}})).filter((x:any)=>x.identifier);const ins=await admin.from("apex_oci_resource_inventory_v1").insert(rows);if(ins.error)throw new Error(`inventory_insert_failed:${ins.error.message}`);}
    const probe={region:creds.region,compartments_http_status:compartments.status,compartments_ok:compartments.ok,compartment_count:Array.isArray(compartments.payload)?compartments.payload.length:null,resource_search_http_status:search.status,resource_search_ok:search.ok,total_resources:items.length,relevant_resources:relevant.length,snapshot_id:snapshot,observed_at:new Date().toISOString()};
    const censusStatus=compartments.ok&&search.ok?"COMPLETE":"PARTIAL";
    const up=await admin.from("apex_oci_control_state_v1").upsert({control_key:"oracle-primary",provider:"oracle_cloud",region:creds.region,oracle_secret_ref:ref,auth_status:"PROVIDER_AUTH_VERIFIED",census_status:censusStatus,resource_counts:counts,last_probe:probe,last_verified_at:new Date().toISOString(),last_census_at:new Date().toISOString(),updated_at:new Date().toISOString()},{onConflict:"control_key"});if(up.error)throw new Error(`control_state_write_failed:${up.error.message}`);
    await admin.rpc("complete_apex_oci_census_gate",{p_error:null});
    return json(200,{ok:true,status:censusStatus,probe,resource_counts:counts});
  }catch(e){const m=e instanceof Error?e.message:"oci_census_failed";await admin.rpc("complete_apex_oci_census_gate",{p_error:m.slice(0,256)});return json(400,{ok:false,error:m.slice(0,256)});}
});