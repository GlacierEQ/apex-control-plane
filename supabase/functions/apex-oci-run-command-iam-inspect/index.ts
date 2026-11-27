import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const H={"content-type":"application/json","cache-control":"no-store,max-age=0","x-content-type-options":"nosniff"};
const enc=new TextEncoder();
function j(s:number,b:unknown){return new Response(JSON.stringify(b),{status:s,headers:H});}
function d64(s:string){const x=atob(s);return Uint8Array.from(x,c=>c.charCodeAt(0));}
function b64(b:Uint8Array){let x="";for(let i=0;i<b.length;i+=0x8000)x+=String.fromCharCode(...b.subarray(i,i+0x8000));return btoa(x);}
function der(p:string){const q=p.trim().replace("-----BEGIN PRIVATE KEY-----","").replace("-----END PRIVATE KEY-----","").replace(/\s+/g,"");const b=d64(q);return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);}
async function get(c:any,path:string){
  const host=`identity.${c.region}.oci.oraclecloud.com`,date=new Date().toUTCString();
  const s=`(request-target): get ${path}\nhost: ${host}\ndate: ${date}`;
  const k=await crypto.subtle.importKey("pkcs8",der(c.private_key_pem),{name:"RSASSA-PKCS1-v1_5",hash:"SHA-256"},false,["sign"]);
  const sig=b64(new Uint8Array(await crypto.subtle.sign({name:"RSASSA-PKCS1-v1_5"},k,enc.encode(s))));
  const auth=`Signature version="1",keyId="${c.tenancy_ocid}/${c.user_ocid}/${c.fingerprint}",algorithm="rsa-sha256",headers="(request-target) host date",signature="${sig}"`;
  const r=await fetch(`https://${host}${path}`,{headers:{date,authorization:auth,accept:"application/json"},signal:AbortSignal.timeout(15000)});
  const t=await r.text();let p:any=null;try{p=t?JSON.parse(t):null}catch{p={body_length:t.length}};
  return {ok:r.ok,status:r.status,payload:p};
}

Deno.serve(async(req:Request)=>{
  if(req.method!=="POST")return j(405,{error:"method_not_allowed"});
  const u=Deno.env.get("SUPABASE_URL"),sr=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if(!u||!sr)return j(500,{error:"configuration_missing"});
  const a=createClient(u,sr,{auth:{persistSession:false,autoRefreshToken:false}});
  const gate=await a.rpc("claim_apex_oci_census_gate");
  if(gate.error||gate.data?.ok!==true)return j(401,{error:gate.error?.message||gate.data?.error||"gate_rejected"});
  try{
    const st=await a.from("apex_oci_control_state_v1").select("oracle_secret_ref").eq("control_key","oracle-primary").single();
    if(st.error||!st.data?.oracle_secret_ref)throw new Error("oracle_secret_missing");
    const rr=await a.rpc("resolve_apex_keymaster_secret_for_broker",{p_secret_ref:st.data.oracle_secret_ref,p_provider:"oracle",p_request_id:`oci-iam-${Date.now()}`,p_actor:"apex-oci-run-command-iam-inspect",p_operation:"inspect_run_command_iam"});
    if(rr.error||typeof rr.data?.secret!=="string")throw new Error(rr.error?.message||"secret_resolution_failed");
    let z=rr.data.secret as string;const c=JSON.parse(z);z="";
    const tenancy=encodeURIComponent(c.tenancy_ocid),user=encodeURIComponent(c.user_ocid);
    const [memberships,groups,policies]=await Promise.all([
      get(c,`/20160918/userGroupMemberships?compartmentId=${tenancy}&userId=${user}&limit=1000`),
      get(c,`/20160918/groups?compartmentId=${tenancy}&limit=1000`),
      get(c,`/20160918/policies?compartmentId=${tenancy}&limit=1000`),
    ]);
    const gl=groups.ok&&Array.isArray(groups.payload)?groups.payload:[];
    const ml=memberships.ok&&Array.isArray(memberships.payload)?memberships.payload:[];
    const names=new Map(gl.map((x:any)=>[String(x.id||""),String(x.name||"")]));
    const userGroups=ml.filter((x:any)=>String(x.state||"")==="ACTIVE").map((x:any)=>({id:x.groupId||null,name:names.get(String(x.groupId||""))||null,state:x.state||null}));
    const pl=policies.ok&&Array.isArray(policies.payload)?policies.payload:[];
    const policyRows=pl.map((x:any)=>({id:x.id||null,name:x.name||null,state:x.lifecycleState||null,statements:Array.isArray(x.statements)?x.statements:[]}));
    const runRelevant=policyRows.filter((p:any)=>p.statements.some((s:any)=>/instance-agent|instance-family|manage all-resources|manage instance/i.test(String(s))));
    await a.rpc("complete_apex_oci_census_gate",{p_outcome_status:"SUCCEEDED",p_detail:{purpose:"inspect_run_command_iam",membership_count:userGroups.length,policy_count:policyRows.length,relevant_policy_count:runRelevant.length}});
    return j(200,{ok:true,user_groups:userGroups,policies:policyRows,relevant_policies:runRelevant,credential_value_returned:false,http_status:{memberships:memberships.status,groups:groups.status,policies:policies.status}});
  }catch(e){const m=e instanceof Error?e.message:"iam_inspect_failed";await a.rpc("complete_apex_oci_census_gate",{p_outcome_status:"FAILED",p_detail:{error:m.slice(0,256),purpose:"inspect_run_command_iam"}}).catch(()=>{});return j(400,{ok:false,error:m.slice(0,256),credential_value_returned:false});}
});