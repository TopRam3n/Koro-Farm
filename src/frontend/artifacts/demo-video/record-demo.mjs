import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
const out='artifacts/demo-video';
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:900},recordVideo:{dir:out,size:{width:1440,height:900}}});
const page=await context.newPage();
const errors=[];
page.on('pageerror',e=>errors.push(e.message));
const pause=ms=>page.waitForTimeout(ms);
const show=async y=>{await page.evaluate(y=>window.scrollTo({top:y,behavior:'smooth'}),y);await pause(1400);};
try {
 await page.goto('http://127.0.0.1:3000');
 await expect(page.getByTestId('committed-kg')).toContainText('500');
 await pause(5000);
 await show(360); await pause(5000);
 const dropout=page.getByRole('button',{name:/Simulate 80/});
 await dropout.hover();await pause(1200);await dropout.click();
 await expect(page.getByTestId('committed-kg')).toContainText('420');
 await pause(6500);
 await page.screenshot({path:out+'/at-risk.png'});
 const recovery=page.getByRole('button',{name:/Run bounded recovery/});
 await recovery.hover();await pause(1800);await recovery.click();
 await expect(page.getByTestId('committed-kg')).toContainText('500');
 await expect(page.getByText('Committed coverage restored')).toBeVisible();
 await pause(7000);
 await page.screenshot({path:out+'/restored.png'});
 await show(820); await pause(6500);
 await show(1300);await pause(5000);
 await show(360);await pause(5000);
 console.log(JSON.stringify({result:'500 ? 420 ? 500 recorded',pageErrors:errors}));
} finally {
 const video=page.video();await context.close();
 await video.saveAs(out+'/KoroFarm-demo.webm');
 await browser.close();
}
