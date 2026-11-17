db["problem.statement"].find({name:"zh.md"}).forEach(function(s){
  var c=s.content||"";
  var i=Math.max(c.lastIndexOf("## 提示"), c.lastIndexOf("## 说明"), c.lastIndexOf("## 数据范围"));
  var hint = i>=0 ? c.slice(i) : "";
  var m=c.match(/##\s*样例输入\s*#?1[\s\S]*?```[^\n]*\n([\s\S]*?)\n```/);
  print(JSON.stringify({docId:s.docId, hint:hint.slice(0,1600), seed:m?m[1]:""}));
});
