const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage();const posts=[];const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://localhost:9312/**',async route=>{
  const request=route.request();
  if(request.url().includes('/api/')){posts.push(request.postDataJSON());return route.fulfill({contentType:'application/json',body:JSON.stringify({ok:true,message:'A jelszavadat beállítottuk.'})});}
  return route.fulfill({contentType:'text/html',body:'<!doctype html><meta charset="utf-8"><main id="login-view" class="hidden"><section class="login-card"><h1>Belépés</h1><p class="muted"></p><form id="old-login"></form><div class="auth-links"></div></section></main>'});
 });
 const token='a'.repeat(43);await page.goto('http://localhost:9312/#set-password='+token);await page.addScriptTag({content:fs.readFileSync('pwa/account_setup.js','utf8')});
 assert.equal(new URL(page.url()).hash,'');assert.equal(await page.evaluate(()=>window.PWA_ACCOUNT_SETUP),true);
 await page.locator('[name=password]').fill('first-password-123');await page.locator('[name=repeat]').fill('different-password-123');await page.getByRole('button',{name:'Jelszó mentése'}).click();assert.equal(posts.length,0);
 await page.locator('[name=repeat]').fill('first-password-123');await page.getByRole('button',{name:'Jelszó mentése'}).click();await page.waitForFunction(()=>document.querySelector('[role=status]').textContent.includes('beállítottuk'));
 assert.equal(posts.length,1);assert.equal(posts[0].token,token);assert.equal(posts[0].password,'first-password-123');assert.equal(await page.locator('[name=password]').inputValue(),'');assert.deepEqual(errors,[]);
 for(const width of [360,900]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);}
 console.log('Password setup browser checks passed: secret removed from URL, mismatch blocked, single POST, successful form clearing.');await browser.close();
})().catch(error=>{console.error(error.message);process.exit(1)});
