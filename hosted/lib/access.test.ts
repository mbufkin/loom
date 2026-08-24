import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  afterAuthPath,
  decideSignIn,
  parseOperatorEmails,
} from "./access";

const OPERATORS = parseOperatorEmails("mbufkin@dallasisd.org");

describe("parseOperatorEmails", () => {
  it("fails closed on empty input", () => {
    assert.deepEqual(parseOperatorEmails(undefined), []);
    assert.deepEqual(parseOperatorEmails(""), []);
  });

  it("splits and lowercases a comma list", () => {
    assert.deepEqual(parseOperatorEmails("A@X.org, b@y.org"), [
      "a@x.org",
      "b@y.org",
    ]);
  });
});

describe("decideSignIn", () => {
  it("denies personal Gmail with no hd", () => {
    const decision = decideSignIn({
      email: "jane@gmail.com",
      emailVerified: true,
      hd: undefined,
      operatorEmails: OPERATORS,
    });
    assert.equal(decision.ok, false);
    if (!decision.ok) assert.equal(decision.reason, "no-hd");
  });

  it("does not treat .edu or email domain as a District", () => {
    const decision = decideSignIn({
      email: "teacher@school.edu",
      emailVerified: true,
      hd: undefined,
      operatorEmails: OPERATORS,
    });
    assert.equal(decision.ok, false);
  });

  it("founds an Admin District from hd, not the email suffix", () => {
    const decision = decideSignIn({
      email: "bob@students.dallasisd.org",
      emailVerified: true,
      hd: "dallasisd.org",
      operatorEmails: OPERATORS,
    });
    assert.deepEqual(decision, {
      ok: true,
      isAdmin: true,
      isOperator: false,
      districtId: "dallasisd.org",
    });
  });

  it("lets the allowlisted Operator in without hd (Gmail is fine)", () => {
    const decision = decideSignIn({
      email: "mbufkin@dallasisd.org",
      emailVerified: true,
      hd: undefined,
      operatorEmails: OPERATORS,
    });
    assert.deepEqual(decision, {
      ok: true,
      isAdmin: false,
      isOperator: true,
      districtId: null,
    });
  });

  it("gives two hats when allowlisted and hd is present", () => {
    const decision = decideSignIn({
      email: "Mbufkin@DallasISD.org",
      emailVerified: true,
      hd: "DallasISD.org",
      operatorEmails: OPERATORS,
    });
    assert.deepEqual(decision, {
      ok: true,
      isAdmin: true,
      isOperator: true,
      districtId: "dallasisd.org",
    });
  });

  it("rejects an unverified Google email even with hd", () => {
    const decision = decideSignIn({
      email: "new@vendor.org",
      emailVerified: false,
      hd: "vendor.org",
      operatorEmails: OPERATORS,
    });
    assert.equal(decision.ok, false);
    if (!decision.ok) assert.equal(decision.reason, "unverified");
  });

  it("does not make anyone Operator when the list is empty", () => {
    const decision = decideSignIn({
      email: "mbufkin@dallasisd.org",
      emailVerified: true,
      hd: undefined,
      operatorEmails: [],
    });
    assert.equal(decision.ok, false);
  });
});

describe("afterAuthPath", () => {
  it("sends two hats to the chooser, never onto the Admin surface by default", () => {
    assert.equal(
      afterAuthPath({ isAdmin: true, isOperator: true }),
      "/hats",
    );
    assert.equal(
      afterAuthPath({ isAdmin: true, isOperator: false }),
      "/workspace",
    );
    assert.equal(
      afterAuthPath({ isAdmin: false, isOperator: true }),
      "/operator",
    );
  });
});
