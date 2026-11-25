// Parses each .kql file with Kusto.Language and reports syntax and semantic errors against minimal table schemas.
// Usage: npm install && node check.js ../../queries/*.kql
global.Bridge = require(__dirname + '/node_modules/@kusto/language-service-next/bridge.js');
require(__dirname + '/node_modules/@kusto/language-service-next/Kusto.Language.Bridge.js');
const fs=require('fs');
const K=Kusto.Language, S=K.Symbols;
function tbl(name, cols){ return new S.TableSymbol.$ctor4(name, cols.map(([n,t])=>new S.ColumnSymbol(n, t))); }
const s=S.ScalarTypes;
const azm=tbl('AzureMetrics',[['TimeGenerated',s.DateTime],['ResourceId',s.String],['Resource',s.String],['ResourceGroup',s.String],['ResourceProvider',s.String],['MetricName',s.String],['Total',s.Real],['Count',s.Real],['Maximum',s.Real],['Minimum',s.Real],['Average',s.Real],['TimeGrain',s.String],['UnitName',s.String]]);
const casl=tbl('ContainerAppSystemLogs',[['TimeGenerated',s.DateTime],['ContainerAppName',s.String],['RevisionName',s.String],['ReplicaName',s.String],['EventSource',s.String],['Reason',s.String],['Type',s.String],['Log',s.String],['Count',s.Int],['EnvironmentName',s.String]]);
const ce=tbl('customEvents',[['timestamp',s.DateTime],['name',s.String],['customDimensions',s.Dynamic]]);
const db=new S.DatabaseSymbol.$ctor1('db',Bridge.toList([azm,casl,ce]),false);
const cl=new S.ClusterSymbol.ctor('c',[db]);
const gs=K.GlobalState.Default.WithCluster(cl).WithDatabase(db);
let bad=0;
for(const f of process.argv.slice(2)){
  const txt=fs.readFileSync(f,'utf8');
  const code=K.KustoCode.ParseAndAnalyze(txt,gs);
  const d=code.GetDiagnostics();
  const n=d.Count;
  const errs=[];
  for(let i=0;i<n;i++){const x=d.getItem(i); if(x.Severity==='Error') errs.push(x.Message+' @'+x.Start);}
  console.log(f, errs.length? 'ERRORS: '+errs.join(' | '):'OK');
  if(errs.length) bad++;
}
process.exit(bad?1:0);
