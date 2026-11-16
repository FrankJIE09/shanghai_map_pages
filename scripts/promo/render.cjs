// Deterministic HTML motion renderer. Requires Node.js, Playwright, Chrome and FFmpeg.
// NODE_PATH=/path/to/node_modules FFMPEG=/path/to/ffmpeg node scripts/promo/render.cjs
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {once}=require('node:events');
const args=process.argv.slice(2),draft=args.includes('--draft'),stills=args.includes('--stills');
const root=path.resolve(__dirname,'../..');
const work=process.env.PROMO_WORK||'/tmp/shanghai-map-promo';
const fps=30,duration=15,scale=draft?2/3:1;
const output=path.join(work,draft?'draft.mp4':'picture.mp4');
(async()=>{
  fs.mkdirSync(work,{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  try{
    const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:scale});
    await page.goto(pathToFileURL(path.join(__dirname,'composition.html')).href);
    await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(im=>im.decode()));});
    // Predecode alternates before deterministic frame stepping.
    await page.evaluate(async()=>{window.preloaded=[];for(const name of ['eat-selected','bars-mobile-detail']){const im=new Image();im.src='sources/'+name+'.png';await im.decode();window.preloaded.push(im);}});
    if(stills){
      for(const t of [.8,3.4,5.2,6.8,8.4,10,13.6]){
        await page.evaluate(t=>window.renderFrame(t),t);
        await page.screenshot({path:path.join(work,`still-${t}.png`)});
      }
      console.log('Representative stills saved to '+work);return;
    }
    const ff=spawn(process.env.FFMPEG||'ffmpeg',['-y','-hide_banner','-loglevel','warning','-f','image2pipe','-framerate',String(fps),'-vcodec','mjpeg','-i','pipe:0','-an','-vf','scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p','-c:v','libx264','-preset',draft?'ultrafast':'medium','-crf',draft?'23':'20','-pix_fmt','yuv420p','-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-r',String(fps),'-movflags','+faststart',output],{stdio:['pipe','inherit','inherit']});
    const finished=once(ff,'close');
    ff.stdin.on('error',e=>console.error('Encoder input:',e.message));
    for(let frame=0;frame<fps*duration;frame++){
      await page.evaluate(t=>window.renderFrame(t),frame/fps);
      const buffer=await page.screenshot({type:'jpeg',quality:draft?86:95});
      if(!ff.stdin.write(buffer))await once(ff.stdin,'drain');
      if(frame%90===0)console.log(`${frame}/${fps*duration} frames`);
    }
    ff.stdin.end();const [code]=await finished;if(code!==0)throw new Error('Encoder exit '+code);
    console.log(output);
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
