import fs from 'node:fs/promises';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
const base=new URL('.',import.meta.url);
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(new URL('oktober_elso_muszak_hub_giriton_2026.xlsx',base).pathname.replace(/^\/(\w:)/,'$1')));
const img=await wb.render({sheetName:'Napi első műszakok',range:'A1:L15',scale:1.4,format:'png'});
await fs.writeFile(new URL('verified_all.png',base),new Uint8Array(await img.arrayBuffer()));
