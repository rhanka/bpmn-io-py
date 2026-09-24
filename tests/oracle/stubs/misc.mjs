// Shared default-absorbing stub for modules only touched inside test bodies:
// `sinon`, `sinon-chai`, `xsd-schema-validator`, `ajv`, `table`,
// `@rollup/plugin-node-resolve`. Mapped in ledger-hooks.mjs.
import { absurd } from './absurd.mjs';

export default absurd();
