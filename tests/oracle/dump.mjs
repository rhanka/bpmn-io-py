// Canonical model/descriptor dumper shared by the oracle differential tests.
//
// Canonical element form: `{ $type, ...set properties in effective-descriptor
// order, $attrs in key order }`. References serialize by id; containment recurses.
// Both this oracle and the Python port implement this exact shape, so canonical
// dumps compare equal across implementations.
import { BpmnModdle } from 'bpmn-moddle';
import { Moddle } from 'moddle';

function dumpItem(item, prop) {
  if (item !== null && typeof item === 'object' && '$type' in item) {
    if (prop && prop.isReference) {
      return item.id ?? null;
    }
    return dumpElement(item);
  }
  return item;
}

function dumpValue(value, prop) {
  if (Array.isArray(value)) {
    return value.map((item) => dumpItem(item, prop));
  }
  return dumpItem(value, prop);
}

export function dumpElement(element) {
  const out = { $type: element.$type };
  const properties = element.$descriptor?.properties ?? [];
  for (const prop of properties) {
    const name = prop.name;
    if (!Object.hasOwn(element, name)) {
      continue;
    }
    out[name] = dumpValue(element[name], prop);
  }
  out.$attrs = { ...(element.$attrs ?? {}) };
  return out;
}

function primitive(value) {
  if (value === null || value === undefined) {
    return null;
  }
  if (['string', 'number', 'boolean'].includes(typeof value)) {
    return value;
  }
  return String(value);
}

export function descriptorDump(packages) {
  const moddle = new Moddle(packages, { strict: true });
  const names = Object.keys(moddle.registry.typeMap).sort();
  const types = [];
  const skipped = [];
  for (const name of names) {
    let descriptor;
    try {
      descriptor = moddle.registry.getEffectiveDescriptor(name);
    } catch (error) {
      // By upstream design, `extends`-bearing trait types have no effective
      // descriptor (addTrait asserts); they are never instantiated directly.
      skipped.push({ name, error: error.message });
      continue;
    }
    types.push({
      name: descriptor.name,
      allTypes: descriptor.allTypes.map((type) => type.name),
      idProperty: descriptor.idProperty ? descriptor.idProperty.name : null,
      bodyProperty: descriptor.bodyProperty ? descriptor.bodyProperty.name : null,
      properties: descriptor.properties.map((prop) => ({
        name: prop.name,
        ns: prop.ns ? prop.ns.name : null,
        type: prop.type,
        isAttr: !!prop.isAttr,
        isMany: !!prop.isMany,
        isReference: !!prop.isReference,
        isId: !!prop.isId,
        isBody: !!prop.isBody,
        inherited: !!prop.inherited,
        ...(prop.default !== undefined ? { default: prop.default } : {}),
      })),
    });
  }
  return { types, skipped };
}

export async function modelDump(xml, type = 'bpmn:Definitions') {
  const moddle = new BpmnModdle();
  const { rootElement, elementsById, references, warnings } = await moddle.fromXML(xml, type);
  const dumped = {};
  for (const [id, element] of Object.entries(elementsById)) {
    dumped[id] = dumpElement(element);
  }
  return {
    root: dumpElement(rootElement),
    elementsById: dumped,
    references: references.map((ref) => ({
      element: ref.element?.id ?? null,
      property: ref.property,
      id: ref.id,
    })),
    warnings: warnings.map((warning) => ({
      message: warning.message,
      element: warning.element ? dumpElement(warning.element) : null,
      property: warning.property ?? null,
      value: primitive(warning.value),
    })),
  };
}

export async function modelSerializeBatch(inputs) {
  const { BpmnModdle } = await import('bpmn-moddle');
  return Promise.all((inputs ?? []).map(async ({ xml, format, preamble }) => {
    try {
      const moddle = new BpmnModdle();
      const { rootElement } = await moddle.fromXML(xml, 'bpmn:Definitions');
      const { xml: serialized } = await moddle.toXML(rootElement, { format, preamble });
      return { xml: serialized };
    } catch (error) {
      return { error: error?.message ?? String(error) };
    }
  }));
}
