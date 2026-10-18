#!/usr/bin/env node
// F1 reference helper: canonical native dumps and writer bytes from the pinned
// literal implementations (bpmn-moddle 10.3.1 / moddle-xml 12.3.1).
//
// Reads one JSON call from argv[2] (or stdin with argv[2] === '@stdin') and
// writes one JSON envelope to stdout. Ops:
//   { op: 'dump', xml, type }          native tree dump incl. generics
//   { op: 'serialize', xml, format, preamble }  literal writer bytes
//   { op: 'descriptorOrder', types }   effective property order per type
import { BpmnModdle } from 'bpmn-moddle';
import process from 'node:process';
import fs from 'node:fs';

const INTERNAL = new Set(['$type', '$parent', '$model', '$descriptor', '$attrs']);

function dumpGeneric(element) {
  const attrs = {};
  for (const key of Object.keys(element)) {
    if (INTERNAL.has(key) || key === '$body' || key === '$children') {
      continue;
    }
    attrs[key] = element[key];
  }
  const out = {
    $any: true,
    name: element.$type,
    uri: element.$descriptor?.ns?.uri ?? null,
    attrs,
  };
  if (Object.hasOwn(element, '$body')) {
    out.body = element.$body;
  }
  if (Object.hasOwn(element, '$children')) {
    out.children = element.$children.map(dumpElement);
  }
  return out;
}

function dumpElement(element) {
  if (element?.$descriptor?.isGeneric) {
    return dumpGeneric(element);
  }
  const out = { $type: element.$type };
  const properties = element.$descriptor?.properties ?? [];
  for (const prop of properties) {
    const name = prop.name;
    if (!Object.hasOwn(element, name)) {
      continue;
    }
    const value = element[name];
    if (prop.isReference) {
      out[name] = Array.isArray(value)
        ? value.map((item) => item?.id ?? null)
        : (value?.id ?? null);
    } else if (Array.isArray(value)) {
      out[name] = value.map((item) =>
        item !== null && typeof item === 'object' && '$type' in item ? dumpElement(item) : item,
      );
    } else if (value !== null && typeof value === 'object' && '$type' in value) {
      out[name] = dumpElement(value);
    } else {
      out[name] = value;
    }
  }
  out.$attrs = { ...(element.$attrs ?? {}) };
  return out;
}

function wireOf(element) {
  if (element?.$descriptor?.isGeneric) {
    const attrs = {};
    for (const key of Object.keys(element)) {
      if (['$type', '$parent', '$model', '$descriptor', '$attrs', '$body', '$children'].includes(key)) {
        continue;
      }
      attrs[key] = element[key];
    }
    const out = { $type: '$any', $name: { qname: element.$type, uri: element.$descriptor?.ns?.uri ?? '' }, $attrs: attrs };
    if (Object.hasOwn(element, '$body')) {
      out.$body = element.$body;
    }
    if (Object.hasOwn(element, '$children')) {
      out.$children = element.$children.map(wireOf);
    }
    return out;
  }
  const out = { $type: element.$type };
  const properties = element.$descriptor?.properties ?? [];
  for (const prop of properties) {
    const name = prop.name;
    if (!Object.hasOwn(element, name)) {
      continue;
    }
    const value = element[name];
    if (prop.isReference) {
      const one = (item) => ({ $ref: item?.id ?? null });
      out[name] = Array.isArray(value) ? value.map(one) : one(value);
    } else if (Array.isArray(value)) {
      out[name] = value.map((item) =>
        item !== null && typeof item === 'object' && '$type' in item ? wireOf(item) : item,
      );
    } else if (value !== null && typeof value === 'object' && '$type' in value) {
      out[name] = wireOf(value);
    } else {
      out[name] = value;
    }
  }
  out.$attrs = { ...(element.$attrs ?? {}) };
  return out;
}

async function wire({ xml, type }) {
  const moddle = new BpmnModdle();
  const { rootElement, warnings } = await moddle.fromXML(xml, type ?? 'bpmn:Definitions');
  return {
    root: wireOf(rootElement),
    warnings: warnings.map((warning) => ({
      message: warning.message,
      property: warning.property ?? null,
      value: typeof warning.value === 'string' ? warning.value : (warning.value ?? null),
    })),
  };
}

async function dump({ xml, type }) {
  const moddle = new BpmnModdle();
  const { rootElement, elementsById, references, warnings } = await moddle.fromXML(
    xml,
    type ?? 'bpmn:Definitions',
  );
  const byId = {};
  for (const [id, element] of Object.entries(elementsById)) {
    byId[id] = dumpElement(element);
  }
  return {
    root: dumpElement(rootElement),
    elementsById: byId,
    references: references.map((ref) => ({
      element: ref.element?.id ?? null,
      property: ref.property,
      id: ref.id,
    })),
    warnings: warnings.map((warning) => ({
      message: warning.message,
      property: warning.property ?? null,
      value: typeof warning.value === 'string' ? warning.value : (warning.value ?? null),
    })),
  };
}

function nativeOf(moddle, node) {
  if (node?.$type === '$any') {
    const element = moddle.createAny(node.$name.qname, node.$name.uri, { ...node.$attrs });
    if ('$body' in node) {
      element.$body = node.$body;
    }
    if ('$children' in node) {
      element.$children = node.$children.map((child) => {
        const built = nativeOf(moddle, child);
        built.$parent = element;
        return built;
      });
    }
    return element;
  }
  throw new Error('genericSerialize supports $any nodes only');
}

async function genericSerialize({ root, format, preamble }) {
  const moddle = new BpmnModdle();
  const element = nativeOf(moddle, root);
  const { xml } = await moddle.toXML(element, {
    format: Boolean(format),
    preamble: preamble !== false,
  });
  return { xml };
}

async function serialize({ xml, format, preamble }) {
  const moddle = new BpmnModdle();
  const { rootElement, warnings } = await moddle.fromXML(xml, 'bpmn:Definitions');
  const { xml: out } = await moddle.toXML(rootElement, {
    format: Boolean(format),
    preamble: preamble !== false,
  });
  return { xml: out, warnings: warnings.map((w) => w.message) };
}

function descriptorOrder({ types }) {
  const moddle = new BpmnModdle();
  const out = {};
  for (const name of types ?? []) {
    const descriptor = moddle.registry.getEffectiveDescriptor(name);
    out[name] = (descriptor.properties ?? []).map((prop) => ({
      name: prop.name,
      type: prop.type,
      isAttr: Boolean(prop.isAttr),
      isMany: Boolean(prop.isMany),
      isReference: Boolean(prop.isReference),
    }));
  }
  return out;
}

async function main() {
  let raw = process.argv[2] ?? '{}';
  if (raw === '@stdin') {
    raw = fs.readFileSync(0, 'utf-8');
  }
  const call = JSON.parse(raw);
  try {
    let result;
    if (call.op === 'dump') {
      result = await dump(call);
    } else if (call.op === 'wire') {
      result = await wire(call);
    } else if (call.op === 'genericSerialize') {
      result = await genericSerialize(call);
    } else if (call.op === 'serialize') {
      result = await serialize(call);
    } else if (call.op === 'descriptorOrder') {
      result = descriptorOrder(call);
    } else {
      throw new Error(`unknown op: ${call.op}`);
    }
    process.stdout.write(`${JSON.stringify({ ok: true, result })}\n`);
  } catch (error) {
    process.stdout.write(
      `${JSON.stringify({ ok: false, error: { message: String(error?.message ?? error) } })}\n`,
    );
  }
}

await main();
