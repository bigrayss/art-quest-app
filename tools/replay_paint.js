#!/usr/bin/env node
/* 专业版的画按日志重放。
 *
 * 用的就是浏览器里画画的那一份 static/paint.js，所以结果和当时画出来的逐像素一样。
 * 平常不用手动跑：artquest/reconstruct.py 重建专业版 session 时会调它。
 *
 *   node tools/replay_paint.js < job.json
 *
 * job = { spec: {width, height, background}, ops: [...], cuts: [做完第几步之后留一张], out: "目录" }
 * 往 out 里写 final.png 和 cut_<n>.png，标准输出一行 JSON：{ engine, checksum, cuts }。
 */
"use strict";
const fs = require("fs"), path = require("path"), zlib = require("zlib");
const Paint = require(path.join(__dirname, "..", "static", "paint.js"));

const CRC = (() => { const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  return t; })();
function crc(buf) { let c = 0xffffffff; for (let i = 0; i < buf.length; i++) c = CRC[(c ^ buf[i]) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; }
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type), data]), sum = Buffer.alloc(4); sum.writeUInt32BE(crc(body));
  return Buffer.concat([len, body, sum]);
}
function writePng(file, px, w, h) {
  const raw = Buffer.alloc((w * 3 + 1) * h);            // 画面是不透明的，存 RGB 就够
  for (let y = 0, o = 0; y < h; y++) { raw[o++] = 0; for (let x = 0; x < w; x++) { const i = (y * w + x) * 4; raw[o++] = px[i]; raw[o++] = px[i + 1]; raw[o++] = px[i + 2]; } }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  fs.writeFileSync(file, Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw, { level: 6 })), chunk("IEND", Buffer.alloc(0))]));
}

const job = JSON.parse(fs.readFileSync(0, "utf8"));
const doc = Paint.create(job.spec), cuts = new Set(job.cuts || []), made = [];
if (job.out) fs.mkdirSync(job.out, { recursive: true });
if (cuts.has(0) && job.out) { writePng(path.join(job.out, "cut_0.png"), doc.flatten(), doc.w, doc.h); made.push(0); }
(job.ops || []).forEach((op, i) => {
  doc.apply(op);
  if (cuts.has(i + 1) && job.out) { writePng(path.join(job.out, `cut_${i + 1}.png`), doc.flatten(), doc.w, doc.h); made.push(i + 1); }
});
const flat = doc.flatten();
if (job.out) writePng(path.join(job.out, "final.png"), flat, doc.w, doc.h);
process.stdout.write(JSON.stringify({ engine: Paint.ENGINE, checksum: Paint.checksum(flat), cuts: made }) + "\n");
