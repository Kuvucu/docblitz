// Впишите номер счётчика Яндекс.Метрики между кавычками, например: const METRIKA_ID = '12345678';
const METRIKA_ID = '';

function goal(name){if(METRIKA_ID&&window.ym)ym(Number(METRIKA_ID),'reachGoal',name)}
if(METRIKA_ID){
  (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};m[i].l=1*new Date();
  k=e.createElement(t),a=e.getElementsByTagName(t)[0];k.async=1;k.src=r;a.parentNode.insertBefore(k,a)})
  (window,document,'script','https://mc.yandex.ru/metrika/tag.js','ym');
  ym(Number(METRIKA_ID),'init',{clickmap:true,trackLinks:true,accurateTrackBounce:true,webvisor:true});
}
