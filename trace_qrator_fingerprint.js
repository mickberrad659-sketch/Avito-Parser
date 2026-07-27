#!/usr/bin/env node
"use strict";

/*
 * Instrument the exact Qrator bundle captured in the HAR.
 *
 * The bundle's MurmurHash3 function is patched in memory so every call records
 * its input before hashing. The script is then executed in an isolated jsdom
 * browser environment; network requests are captured rather than transmitted.
 */

const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const workspace = __dirname;
const bundlePath = path.join(workspace, "f1b0f8f3fb96fe30a8e6.js");
const outputPath = path.join(workspace, "qrator-fingerprint-trace.json");
const rawOutputPath = path.join(workspace, "qrator-raw-before-transform.txt");

const originalSource = fs.readFileSync(bundlePath, "utf8");
const rawSuffix = process.env.QRATOR_RAW_SUFFIX || "";
const hashReturn = "H$^=H$ >>> 16;return H$;};return {a1E3adp:a1E3adp};";
const instrumentedReturn = [
  "H$^=H$ >>> 16;",
  "try{",
  "var traceRoot=typeof globalThis==='object'?globalThis:window;",
  "var trace=traceRoot.__qratorHashTrace||(traceRoot.__qratorHashTrace=[]);",
  "var rawValue=typeof d3==='string'?d3:String(d3);",
  "trace.push({",
  "raw:rawValue,",
  "length:V3,",
  "seed:z0,",
  "hashUnsigned:H$>>>0,",
  "hashHex:(H$>>>0).toString(16).padStart(8,'0')",
  "});",
  "}catch(traceError){}",
  "return H$;",
  "};return {a1E3adp:a1E3adp};",
].join("");

const matchCount = originalSource.split(hashReturn).length - 1;
if (matchCount !== 1) {
  throw new Error(`Expected one MurmurHash3 return site, found ${matchCount}`);
}
let instrumentedSource = originalSource.replace(hashReturn, instrumentedReturn);
const cipherFunctionStart = "function g(B3,f_){";
if (instrumentedSource.split(cipherFunctionStart).length - 1 !== 1) {
  throw new Error("Expected one Qrator cipher function");
}
instrumentedSource = instrumentedSource.replace(
  cipherFunctionStart,
  [
    cipherFunctionStart,
    "try{",
    "var cipherRoot=typeof globalThis==='object'?globalThis:window;",
    "var cipherTrace=cipherRoot.__qratorCipherTrace||(cipherRoot.__qratorCipherTrace=[]);",
    "cipherTrace.push({raw:String(B3),key:Array.prototype.slice.call(f_)});",
    "}catch(cipherTraceError){}",
  ].join(""),
);

const requests = [];
const runtimeErrors = [];
const assemblyTrace = [];
let generatedPixelUrl = null;

const virtualConsole = new VirtualConsole();
virtualConsole.on("jsdomError", (error) => runtimeErrors.push(error.message));
virtualConsole.on("error", (error) => runtimeErrors.push(String(error)));

const dom = new JSDOM(
  `<!doctype html><html><body><script>${instrumentedSource}</script></body></html>`,
  {
    url: "https://www.avito.ru/qrator-trace",
    runScripts: "dangerously",
    pretendToBeVisual: true,
    virtualConsole,
    beforeParse(window) {
      const nativeJoin = window.Array.prototype.join;
      window.Array.prototype.join = function tracedJoin(separator) {
        const originalResult = nativeJoin.call(this, separator);
        const isRawFingerprint = separator === ";" && this.length === 141;
        const result = isRawFingerprint
          ? `${originalResult}${window.__qratorRawSuffix}`
          : originalResult;
        if (result.length >= 50) {
          assemblyTrace.push({
            operation: "Array.join",
            stack: new Error("Qrator assembly trace").stack,
            separator: separator === undefined ? "," : String(separator),
            itemCount: this.length,
            items: Array.from(this, (item) => {
              const text = String(item);
              return text.length > 1000
                ? `${text.slice(0, 1000)}…[${text.length - 1000} chars omitted]`
                : text;
            }),
            result:
              result.length > 4000
                ? `${result.slice(0, 4000)}…[${result.length - 4000} chars omitted]`
                : result,
          });
        }
        return result;
      };

      class CapturedXMLHttpRequest {
        constructor() {
          this.headers = {};
          this.readyState = 0;
          this.status = 200;
          this.responseText = '"TRACE_FT_VALUE"';
          this.response = this.responseText;
        }

        open(method, url, async = true) {
          this.method = method;
          this.url = url;
          this.async = async;
        }

        setRequestHeader(name, value) {
          this.headers[name] = value;
        }

        addEventListener(name, callback) {
          this[`on${name}`] = callback;
        }

        send(body) {
          requests.push({
            transport: "XMLHttpRequest",
            method: this.method,
            url: this.url,
            headers: this.headers,
            body: body == null ? null : String(body),
          });
          this.readyState = 4;
          if (typeof this.onload === "function") this.onload();
          if (typeof this.onreadystatechange === "function") this.onreadystatechange();
        }
      }

      class CapturedImage {
        set src(value) {
          requests.push({ transport: "Image", method: "GET", url: value });
          if (value.includes("/web/1/u?")) generatedPixelUrl = value;
        }

        get src() {
          return "";
        }
      }

      window.XMLHttpRequest = CapturedXMLHttpRequest;
      window.Image = CapturedImage;
      window.__qratorRawSuffix = rawSuffix;
      window.HTMLCanvasElement.prototype.getContext = () => null;
    },
  },
);

setTimeout(() => {
  const ftRequest = requests.find((request) => request.url === "/web/2/ft");
  const trace = Array.from(dom.window.__qratorHashTrace || []);
  const cipherTrace = Array.from(dom.window.__qratorCipherTrace || []);
  const output = {
    note:
      "Values describe the jsdom environment. Run the instrumented bundle in the target browser to obtain that browser's exact raw values.",
    bundle: path.basename(bundlePath),
    murmurHash: "MurmurHash3 x86 32-bit",
    hashCalls: trace,
    cipherCalls: cipherTrace,
    assemblyTrace,
    submittedFtRequest: ftRequest || null,
    generatedPixelUrl,
    documentCookie: dom.window.document.cookie,
    runtimeErrors,
  };

  fs.writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
  const rawAssembly = assemblyTrace.find(
    (entry) => entry.operation === "Array.join" && entry.separator === ";",
  );
  if (rawAssembly) {
    fs.writeFileSync(rawOutputPath, `${rawAssembly.result}\n`, "utf8");
  }
  console.log(`Saved ${trace.length} pre-hash values to ${outputPath}`);
  if (rawAssembly) console.log(`Saved raw assembled text to ${rawOutputPath}`);
  if (ftRequest) console.log("Captured /web/2/ft form data");
  if (generatedPixelUrl) console.log(`Captured pixel URL: ${generatedPixelUrl}`);
  dom.window.close();
}, 1000);
