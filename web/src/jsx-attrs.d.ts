// Attributes we set through Solid's `attr:` escape hatch.
//
// `inert` is on Solid's boolean list as an HTMLElement *property*, so plain
// `inert={…}` compiles to `el.inert = …`. That is right in a browser and a
// silent no-op anywhere the property is unimplemented (jsdom), while the
// attribute is what inert semantics key on either way. `attr:inert` sets the
// attribute — and needs this declaration to be typed, since Solid derives the
// `attr:` keys from an interface that is empty until an app fills it in.

import "solid-js";

declare module "solid-js" {
  namespace JSX {
    interface ExplicitAttributes {
      inert: string | undefined;
    }
  }
}
