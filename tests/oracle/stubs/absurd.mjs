// Universal absorbing stub value for modules the ledger dry-run never executes.
//
// Anything can be done with it (called, constructed, chained, awaited) without
// throwing, so spec-file top-level code that touches stubbed helpers still loads.
// Only `it()`/`describe()` registrations matter here; test bodies never run.

function makeAbsurd() {
  const fn = function () {
    return proxy;
  };
  const proxy = new Proxy(fn, {
    get(_target, prop) {
      if (prop === Symbol.toPrimitive) {
        return () => 0;
      }
      if (prop === 'then') {
        return undefined;
      }
      if (prop === 'toString' || prop === Symbol.for('nodejs.util.inspect.custom')) {
        return () => '[stub]';
      }
      return proxy;
    },
    apply() {
      return proxy;
    },
    construct() {
      return proxy;
    },
    has() {
      return true;
    },
  });
  return proxy;
}

export function absurd() {
  return makeAbsurd();
}
