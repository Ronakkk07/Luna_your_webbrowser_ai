#!/usr/bin/env python3
"""Fetch and prepare the offline speech assets for the Luna extension.

Downloads the vosk-browser WASM bundle and the small English model, then patches
the bundle so its Web Worker loads from a packaged file instead of a blob: URL
(Manifest V3's Content-Security-Policy forbids blob: workers).

Outputs (all git-ignored, ~46 MB total):
    extension/vendor/vosk.js          (patched loader, ~30 KB)
    extension/vendor/vosk-worker.js   (extracted worker + inlined WASM, ~4.3 MB)
    extension/models/model.tar.gz     (vosk-model-small-en-us-0.15, ~40 MB)

Usage:
    python scripts/build_vosk_vendor.py
"""
import base64
import re
import sys
import urllib.request
from pathlib import Path

VOSK_JS_URL = "https://cdn.jsdelivr.net/npm/vosk-browser@0.0.8/dist/vosk.js"
MODEL_URL = (
    "https://ccoreilly.github.io/vosk-browser/models/"
    "vosk-model-small-en-us-0.15.tar.gz"
)

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "extension" / "vendor"
MODELS = ROOT / "extension" / "models"


CRAFT_INVOKER_CLOSURE = (
    "function craftInvokerFunction(humanName,argTypes,classType,cppInvokerFunc,cppTargetFunc){"
    "var argCount=argTypes.length;"
    "if(argCount<2){throwBindingError(\"argTypes array size mismatch! Must at least get return value and 'this' types!\");}"
    "var isClassMethodFunc=argTypes[1]!==null&&classType!==null;"
    "var needsDestructorStack=false;"
    "for(var i=1;i<argTypes.length;++i){if(argTypes[i]!==null&&argTypes[i].destructorFunction===undefined){needsDestructorStack=true;break;}}"
    "var returns=argTypes[0].name!==\"void\";"
    "var expectedArgCount=argCount-2;"
    "var argsWired=new Array(expectedArgCount);"
    "var invokerFuncArgs=[];"
    "var destructors=[];"
    "var invokerFn=function(){"
    "if(arguments.length!==expectedArgCount){throwBindingError(\"function \"+humanName+\" called with \"+arguments.length+\" arguments, expected \"+expectedArgCount+\" args!\");}"
    "destructors.length=0;"
    "var thisWired;"
    "invokerFuncArgs.length=isClassMethodFunc?1:0;"
    "if(isClassMethodFunc){thisWired=argTypes[1].toWireType(destructors,this);invokerFuncArgs[0]=thisWired;}"
    "for(var i=0;i<expectedArgCount;++i){argsWired[i]=argTypes[i+2].toWireType(destructors,arguments[i]);invokerFuncArgs.push(argsWired[i]);}"
    "var returnVal=cppInvokerFunc.apply(null,[cppTargetFunc].concat(invokerFuncArgs));"
    "if(needsDestructorStack){runDestructors(destructors);}"
    "else{for(var i=isClassMethodFunc?1:2;i<argTypes.length;++i){var param=i===1?thisWired:argsWired[i-2];if(argTypes[i].destructorFunction!==null){argTypes[i].destructorFunction(param);}}}"
    "if(returns){return argTypes[0].fromWireType(returnVal);}"
    "};"
    "return createNamedFunction(humanName,invokerFn);}"
)


def _patch_craft_invoker(src):
    s = src.find("function craftInvokerFunction(")
    if s < 0:
        sys.exit("ERROR: craftInvokerFunction not found")
    end = "return invokerFunction}"
    e = src.find(end, s) + len(end)
    return src[:s] + CRAFT_INVOKER_CLOSURE + src[e:]


EMVAL_METHOD_CALLER_CLOSURE = (
    "function __emval_get_method_caller(argCount,argTypes){"
    "var types=__emval_lookupTypes(argCount,argTypes);"
    "var retType=types[0];"
    "var argN=argCount-1;"
    "var invokerFunction=function(handle,name,destructors,args){"
    "var offset=0;var callArgs=new Array(argN);"
    "for(var i=0;i<argN;++i){callArgs[i]=types[i+1].readValueFromPointer(args+offset);offset+=types[i+1].argPackAdvance;}"
    "var rv=handle[name].apply(handle,callArgs);"
    "for(var i=0;i<argN;++i){if(types[i+1].deleteObject){types[i+1].deleteObject(callArgs[i]);}}"
    "if(!retType.isVoid){return retType.toWireType(destructors,rv);}"
    "};"
    "return __emval_addMethodCaller(invokerFunction)}"
)


def _patch_emval_method_caller(src):
    s = src.find("function __emval_get_method_caller(")
    if s < 0:
        sys.exit("ERROR: __emval_get_method_caller not found")
    end = "return __emval_addMethodCaller(invokerFunction)}"
    e = src.find(end, s) + len(end)
    return src[:s] + EMVAL_METHOD_CALLER_CLOSURE + src[e:]


def fetch(url):
    print(f"  downloading {url}")
    with urllib.request.urlopen(url, timeout=300) as resp:
        return resp.read()


def build_vendor():
    VENDOR.mkdir(parents=True, exist_ok=True)
    src = fetch(VOSK_JS_URL).decode("utf-8", "replace")

    m = re.search(r"createBase64WorkerFactory\('([A-Za-z0-9+/=]+)'", src)
    if not m:
        sys.exit("ERROR: could not find embedded worker in vosk.js")
    b64 = m.group(1)

    worker_src = base64.b64decode(b64).decode("utf-8", "replace")
    # MV3 CSP forbids JS eval/new Function. Emscripten's Embind uses new Function()
    # only to give bound functions a cosmetic name; rewrite it to return the body.
    worker_src, n = re.subn(
        r"function createNamedFunction\(name,body\)\{.*?\(body\)\}",
        "function createNamedFunction(name,body){return body}",
        worker_src, count=1, flags=re.DOTALL,
    )
    if n != 1 or "new Function(" in worker_src:
        sys.exit("ERROR: failed to remove new Function() from the worker")

    # Embind JIT-compiles its method invokers via `new_(Function, args)` (an
    # obfuscated `new Function`). Replace craftInvokerFunction with emscripten's
    # eval-free closure version (equivalent to compiling with DYNAMIC_EXECUTION=0).
    worker_src = _patch_craft_invoker(worker_src)
    worker_src = _patch_emval_method_caller(worker_src)
    if "new_(Function" in worker_src:
        sys.exit("ERROR: an eval-based invoker survived patching")

    # Build marker so it's obvious in the offscreen console which code is running.
    worker_src = 'console.log("[vosk-worker] eval-free build loaded");\n' + worker_src
    (VENDOR / "vosk-worker.js").write_text(worker_src, encoding="utf-8")
    print(f"  wrote vendor/vosk-worker.js ({len(worker_src):,} bytes)")

    patched = src.replace(
        "return new Worker(url, options);",
        'return new Worker(chrome.runtime.getURL("vendor/vosk-worker.js"), options);',
    )
    if patched == src:
        sys.exit("ERROR: worker loader line not found to patch")
    patched = patched.replace(f"createBase64WorkerFactory('{b64}'", "createBase64WorkerFactory(''")
    if "createModel" not in patched:
        sys.exit("ERROR: patched vosk.js is missing the createModel API")
    (VENDOR / "vosk.js").write_text(patched, encoding="utf-8")
    print(f"  wrote vendor/vosk.js ({len(patched):,} bytes)")


def build_model():
    MODELS.mkdir(parents=True, exist_ok=True)
    data = fetch(MODEL_URL)
    (MODELS / "model.tar.gz").write_bytes(data)
    print(f"  wrote models/model.tar.gz ({len(data):,} bytes)")


if __name__ == "__main__":
    print("Building Vosk vendor bundle...")
    build_vendor()
    print("Fetching model...")
    build_model()
    print("Done.")
