.PHONY: ui ui-clean

STATIC_DIR := minimal_agent/src/minimal_agent/server/static

# Build the web UI and bundle it into the package so `App` serves it at "/".
# Uses `npx vite build` rather than `npm run build`: the tsc step in the npm
# script currently fails on upstream @assistant-ui type issues unrelated to
# bundling.
ui:
	cd web && npm install && npx vite build
	rm -rf $(STATIC_DIR)
	mkdir -p $(STATIC_DIR)
	cp -r web/dist/* $(STATIC_DIR)/

# Remove the bundled UI (App falls back to its placeholder page).
ui-clean:
	rm -rf $(STATIC_DIR)
