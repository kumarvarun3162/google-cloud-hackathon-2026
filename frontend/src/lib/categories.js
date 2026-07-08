// A restrained categorical palette derived from the brand family (teal/blue
// range) plus the marigold accent for one category — kept to 5 hues so the
// map reads as a legend, not a rainbow chart.
export const CATEGORIES = [
  { id: "water_supply", color: "#0F6172", labelKey: "categories.water_supply" },
  { id: "road_damage", color: "#E98A15", labelKey: "categories.road_damage" },
  { id: "electricity", color: "#5B3E9A", labelKey: "categories.electricity" },
  { id: "drainage", color: "#1F9D65", labelKey: "categories.drainage" },
  { id: "waste_management", color: "#946B3A", labelKey: "categories.waste_management" },
  { id: "street_lighting", color: "#2B6FB3", labelKey: "categories.street_lighting" },
];

export function getCategory(id) {
  return CATEGORIES.find((c) => c.id === id) ?? CATEGORIES[0];
}
