import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const PROTOCOL_VERSION = "2025-06-18";
if (!SUPABASE_URL || !SERVICE_ROLE) throw new Error("supabase_runtime_unavailable");

type Json = Record<string, unknown>;
type RpcId = string | number | null;
type ToolDef = { name: string; description: string; inputSchema: Json; plugin: "github" | "notion" };

const CHILDREN = {
  github: `${SUPABASE_URL}/functions/v1/apex-direct-github-mcp`,
  notion: `${SUPABASE_URL}/functions/v1/apex-direct-notion-mcp`,
} as const;

const TOOLS: ToolDef[] = [
  { name:"github_repo_get", description:"Read GlacierEQ GitHub repository metadata through the owned direct MCP.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"}},required:["repository"],additionalProperties:false}},
  { name:"github_contents_get", description:"Read a GitHub file or directory directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},path:{type:"string"},ref:{type:"string"}},required:["repository","path"],additionalProperties:false}},
  { name:"github_tree_list", description:"List a GitHub repository tree directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},ref:{type:"string"}},required:["repository"],additionalProperties:false}},
  { name:"github_branches_list", description:"List GitHub branches directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},per_page:{type:"integer",minimum:1,maximum:100}},required:["repository"],additionalProperties:false}},
  { name:"github_commits_list", description:"List GitHub commits directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},ref:{type:"string"},path:{type:"string"},per_page:{type:"integer",minimum:1,maximum:100}},required:["repository"],additionalProperties:false}},
  { name:"github_code_search", description:"Search code in one GlacierEQ repository directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},query:{type:"string"},per_page:{type:"integer",minimum:1,maximum:100}},required:["repository","query"],additionalProperties:false}},
  { name:"github_issues_list", description:"List GitHub issues directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},state:{type:"string",enum:["open","closed","all"]},per_page:{type:"integer",minimum:1,maximum:100}},required:["repository"],additionalProperties:false}},
  { name:"github_issue_get", description:"Read one GitHub issue directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},number:{type:"integer",minimum:1}},required:["repository","number"],additionalProperties:false}},
  { name:"github_pulls_list", description:"List GitHub pull requests directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},state:{type:"string",enum:["open","closed","all"]},per_page:{type:"integer",minimum:1,maximum:100}},required:["repository"],additionalProperties:false}},
  { name:"github_pull_get", description:"Read one GitHub pull request directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},number:{type:"integer",minimum:1}},required:["repository","number"],additionalProperties:false}},
  { name:"github_actions_runs", description:"List GitHub Actions runs directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},branch:{type:"string"},status:{type:"string"},per_page:{type:"integer",minimum:1,maximum:100}},required:["repository"],additionalProperties:false}},
  { name:"github_branch_create", description:"Create a governed non-default GitHub branch through the direct connector.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},branch:{type:"string"},base_branch:{type:"string"},request_id:{type:"string",minLength:8}},required:["repository","branch","request_id"],additionalProperties:false}},
  { name:"github_contents_put", description:"Write UTF-8 repository content on a non-default branch with direct connector readback.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},path:{type:"string"},branch:{type:"string"},message:{type:"string"},content:{type:"string"},request_id:{type:"string",minLength:8}},required:["repository","path","branch","message","content","request_id"],additionalProperties:false}},
  { name:"github_issue_create", description:"Create a GitHub issue directly with durable connector receipt.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},title:{type:"string"},body:{type:"string"},labels:{type:"array",items:{type:"string"}},assignees:{type:"array",items:{type:"string"}},request_id:{type:"string",minLength:8}},required:["repository","title","request_id"],additionalProperties:false}},
  { name:"github_issue_comment", description:"Comment on a GitHub issue directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},number:{type:"integer",minimum:1},body:{type:"string"},request_id:{type:"string",minLength:8}},required:["repository","number","body","request_id"],additionalProperties:false}},
  { name:"github_pull_create", description:"Create a GitHub pull request directly when the underlying connector route is authorized.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},title:{type:"string"},body:{type:"string"},head:{type:"string"},base:{type:"string"},draft:{type:"boolean"},request_id:{type:"string",minLength:8}},required:["repository","title","head","base","request_id"],additionalProperties:false}},
  { name:"github_pull_comment", description:"Comment on a GitHub pull request directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},number:{type:"integer",minimum:1},body:{type:"string"},request_id:{type:"string",minLength:8}},required:["repository","number","body","request_id"],additionalProperties:false}},
  { name:"github_workflow_dispatch", description:"Dispatch a GitHub Actions workflow directly.", plugin:"github", inputSchema:{type:"object",properties:{repository:{type:"string"},workflow_id:{oneOf:[{type:"string"},{type:"integer"}]},ref:{type:"string"},inputs:{type:"object"},request_id:{type:"string",minLength:8}},required:["repository","workflow_id","ref","request_id"],additionalProperties:false}},
  { name:"notion_search", description:"Search the directly connected Notion workspace without Smithery.", plugin:"notion", inputSchema:{type:"object",properties:{query:{type:"string",minLength:1,maxLength:500},limit:{type:"integer",minimum:1,maximum:100}},required:["query"],additionalProperties:false}},
  { name:"notion_page_get", description:"Read a Notion page directly from the Notion API.", plugin:"notion", inputSchema:{type:"object",properties:{page_id:{type:"string",minLength:16,maxLength:64}},required:["page_id"],additionalProperties:false}},
  { name:"notion_block_children", description:"Read Notion block children directly, with pagination.", plugin:"notion", inputSchema:{type:"object",properties:{block_id:{type:"string",minLength:16,maxLength:64},page_size:{type:"integer",minimum:1,maximum:100},start_cursor:{type:"string"}},required:["block_id"],additionalProperties:false}},
  { name:"apex_plugins_list", description:"List the owned direct MCP plugins currently federated by this GlacierEQ MCP fabric.", plugin:"github", inputSchema:{type:"object",properties:{},additionalProperties:false}}
];

const byName = new Map(TOOLS.map(t => [t.name,t]));
function decodeJwt(req:Request):Json { const a=req.headers.get("authorization")||""; if(!a.startsWith("Bearer "))return{}; const p=a.slice(7).trim().split("."); if(p.length!==3)return{}; try{const n=p[1].replace(/-/g,"+").replace(/_/g,"/").padEnd(Math.ceil(p[1].length/4)*4,"=");return JSON.parse(atob(n));}catch{return{}} }
function respond(body:unknown,status=200){return new Response(body===null?null:JSON.stringify(body),{status,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store","x-content-type-options":"nosniff","mcp-protocol-version":PROTOCOL_VERSION}})}
function ok(id:RpcId,result:unknown){return{jsonrpc:"2.0",id,result}}
function err(id:RpcId,code:number,message:string,data?:unknown){return{jsonrpc:"2.0",id,error:{code,message,...(data===undefined?{}:{data})}}}

async function forward(plugin:"github"|"notion", payload:Json):Promise<Json>{
  const r=await fetch(CHILDREN[plugin],{method:"POST",headers:{authorization:`Bearer ${SERVICE_ROLE}`,apikey:SERVICE_ROLE,"content-type":"application/json","x-glaciereq-origin":"apex-direct-mcp-fabric"},body:JSON.stringify(payload),signal:AbortSignal.timeout(60_000)});
  const raw=await r.text(); let data:unknown=raw; try{data=raw?JSON.parse(raw):{}}catch{}
  if(!r.ok)throw new Error(`child_${plugin}_http_${r.status}:${typeof data==="string"?data.slice(0,1000):JSON.stringify(data).slice(0,1000)}`);
  return (data&&typeof data==="object"&&!Array.isArray(data)?data:{data}) as Json;
}

Deno.serve(async(req:Request)=>{
  if(req.method!=="POST")return respond({ok:false,error:"method_not_allowed"},405);
  const claims=decodeJwt(req); if(claims.role!=="service_role")return respond(err(null,-32001,"service_role_required"),403);
  let rpc:Json; try{const v=await req.json(); if(!v||typeof v!=="object"||Array.isArray(v))throw new Error(); rpc=v as Json;}catch{return respond(err(null,-32700,"Parse error"),400)}
  const id=(rpc.id??null) as RpcId; const method=typeof rpc.method==="string"?rpc.method:""; const params=rpc.params&&typeof rpc.params==="object"&&!Array.isArray(rpc.params)?rpc.params as Json:{};
  if(rpc.jsonrpc!=="2.0")return respond(err(id,-32600,"Invalid Request"),400);
  if(method==="initialize")return respond(ok(id,{protocolVersion:PROTOCOL_VERSION,capabilities:{tools:{listChanged:false}},serverInfo:{name:"glaciereq-direct-mcp-fabric",version:"1.0.0"},instructions:"GlacierEQ-owned direct MCP fabric. Active provider plugins: GitHub Direct and Notion Direct. No Smithery dependency or quota on these routes."}));
  if(method==="notifications/initialized")return new Response(null,{status:204});
  if(method==="ping")return respond(ok(id,{}));
  if(method==="tools/list")return respond(ok(id,{tools:TOOLS.map(({plugin,...t})=>({...t,annotations:{readOnlyHint:!t.name.includes("create")&&!t.name.includes("put")&&!t.name.includes("comment")&&!t.name.includes("dispatch"),destructiveHint:false}}))}));
  if(method==="tools/call"){
    const name=typeof params.name==="string"?params.name:""; const tool=byName.get(name); if(!tool)return respond(err(id,-32602,"Unknown tool",{name}),400);
    if(name==="apex_plugins_list")return respond(ok(id,{content:[{type:"text",text:JSON.stringify({plugins:[{key:"github.direct_mcp",server:"apex-direct-github-mcp",tool_count:18},{key:"notion.direct_mcp",server:"apex-direct-notion-mcp",tool_count:3}],smithery_required:false})}],structuredContent:{plugins:[{key:"github.direct_mcp",server:"apex-direct-github-mcp",tool_count:18},{key:"notion.direct_mcp",server:"apex-direct-notion-mcp",tool_count:3}],smithery_required:false},isError:false}));
    const args=params.arguments&&typeof params.arguments==="object"&&!Array.isArray(params.arguments)?params.arguments as Json:{};
    try{return respond(await forward(tool.plugin,{jsonrpc:"2.0",id,method:"tools/call",params:{name,arguments:args}}));}catch(e){const m=e instanceof Error?e.message:String(e);return respond(ok(id,{content:[{type:"text",text:m}],structuredContent:{ok:false,error:m,tool:name,plugin:tool.plugin},isError:true}));}
  }
  return respond(err(id,-32601,"Method not found",{method}),404);
});