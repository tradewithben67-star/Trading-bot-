/* Quelle fuer three-paket.min.js: three.js samt den Zusaetzen, die welt.html
   braucht, als ein klassisches Skript (laeuft auch per file://).

   Neu bauen (three@0.159.0 und esbuild installiert):
     npx esbuild tools/videos/vendor/three-paket.js --bundle --minify \
       --format=iife --outfile=tools/videos/vendor/three-paket.min.js */
import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { Reflector } from 'three/examples/jsm/objects/Reflector.js';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';

window.THREE = Object.assign({}, THREE, { EffectComposer, RenderPass, UnrealBloomPass, OutputPass, Reflector, RoundedBoxGeometry });
