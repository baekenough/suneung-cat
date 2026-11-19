import { parse, VERSION } from 'kordoc';

const result = await parse(process.argv[2], { ocr: false, images: false });
if (!result.success) {
  throw new Error(`kordoc: ${result.error}`);
}
process.stdout.write(JSON.stringify({ version: VERSION, pageCount: result.pageCount, blocks: result.blocks }));
