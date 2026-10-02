/**
 * Turning the server's rejections into something a customer can act on.
 *
 * WHY THESE TESTS AND NOT OTHERS
 *
 * This is the layer that failed in front of a real customer. The claim form
 * submits at the END of the costs step, so a field rejected by the server
 * surfaces steps away from where it was typed -- and what surfaced was
 *
 *     String should have at most 20 characters
 *
 * in English, in a Hebrew form, naming no field. There is nothing a person
 * can do with that. Each test below is one property of the repair.
 */

import { describe, expect, it } from "vitest";

import { strings } from "@/lib/strings";
import { __testing } from "@/lib/api";

const { describeValidationError } = __testing;

describe("describeValidationError", () => {
  it("names the field, in Hebrew, for the error a customer actually hit", () => {
    /**
     * The exact payload FastAPI sends for a booking reference over the
     * limit. `loc` carried the field name the whole time and was being
     * thrown away.
     */
    const message = describeValidationError({
      loc: ["body", "booking_reference"],
      msg: "String should have at most 64 characters",
    });

    expect(message).toContain("מספר הזמנה");
    expect(message).toContain("64");
    expect(message).not.toMatch(/[A-Za-z]{4,}/);
  });

  it("finds the field inside a list, not the list index", () => {
    /**
     * Passengers and expenses are arrays, so `loc` looks like
     * ["body", "passengers", 0, "full_name"]. Taking the last element
     * blindly would work here but taking loc[1] would say "passengers",
     * and a numeric index must never be mistaken for a field name.
     */
    const message = describeValidationError({
      loc: ["body", "passengers", 0, "full_name"],
      msg: "String should have at most 200 characters",
    });

    expect(message).toContain("שם הנוסע");
  });

  it("still says something useful for a message it cannot translate", () => {
    /**
     * The translator only knows the handful of constraints we actually set.
     * An unfamiliar message must not be swallowed or replaced with a guess:
     * the field name alone turns an unusable error into a locatable one,
     * and the original wording is better than silence about the rest.
     */
    const message = describeValidationError({
      loc: ["body", "contact_email"],
      msg: "value is not a valid email address",
    });

    expect(message).toContain("אימייל");
    expect(message).toContain("value is not a valid email address");
  });

  it("does not invent a field name it does not have", () => {
    /**
     * A rejection on a field with no Hebrew name must degrade to the raw
     * message rather than to an empty prefix like ": ..." -- which reads
     * as a rendering bug and tells the customer even less than before.
     */
    const message = describeValidationError({
      loc: ["body", "some_field_nobody_named"],
      msg: "Input should be a valid integer",
    });

    expect(message).toBe("Input should be a valid integer");
  });

  it("drops Pydantic's 'Value error,' prefix", () => {
    /**
     * Our own validators raise through ValueError, and Pydantic prefixes
     * the result. The prefix is an implementation detail of the server and
     * means nothing to the person reading it.
     */
    const message = describeValidationError({
      loc: ["body", "currency"],
      msg: "Value error, unsupported currency",
    });

    expect(message).not.toContain("Value error");
  });

  it("returns nothing for an empty message rather than a bare field name", () => {
    /**
     * `filter(Boolean)` upstream drops empties. A field name on its own
     * would survive that filter and render as a complaint with no content.
     */
    expect(
      describeValidationError({ loc: ["body", "contact_name"], msg: "" }),
    ).toBe("");
  });
});

describe("the field-name table", () => {
  it("covers every field the claim form can submit", () => {
    /**
     * The table is the whole repair, and it is a hand-written list that
     * will fall behind the schema. This does not catch a new server field
     * -- nothing in this language can -- but it does catch a rename or a
     * deletion on this side, which is the likelier accident.
     */
    for (const field of [
      "contact_name",
      "contact_email",
      "booking_reference",
      "amount",
      "full_name",
    ]) {
      expect(strings.errors.fieldNames[field], field).toBeTruthy();
    }
  });
});
