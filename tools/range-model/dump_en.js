db["problem.statement"].find({name:"en.md"}).forEach(function(s){
  var c=s.content||"";
  var i=Math.max(c.lastIndexOf("## Hints"), c.lastIndexOf("## Hint"), c.lastIndexOf("## Constraints"), c.lastIndexOf("## Notes"));
  var hint = i>=0 ? c.slice(i) : "";
  print(JSON.stringify({docId:s.docId, hint:hint.slice(0,1600)}));
});
