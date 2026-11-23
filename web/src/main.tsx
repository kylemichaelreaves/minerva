import { render } from "@solidjs/web";
import App from "~/App";
import "~/styles/styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing in index.html");

render(() => <App />, root);
