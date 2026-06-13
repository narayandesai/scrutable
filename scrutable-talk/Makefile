SLIDES := slides.md
OUT_DIR := out
CHROME_WRAPPER := $(OUT_DIR)/chromium-nosandbox

.PHONY: pdf html watch clean

$(CHROME_WRAPPER): | $(OUT_DIR)
	printf '#!/bin/sh\nexec chromium --no-sandbox --disable-setuid-sandbox "$$@"\n' > $@
	chmod +x $@

pdf: $(CHROME_WRAPPER)
	marp $(SLIDES) --pdf --output $(OUT_DIR)/slides.pdf --browser-path=$(CHROME_WRAPPER)

html: $(OUT_DIR)
	marp $(SLIDES) --output $(OUT_DIR)/slides.html

watch:
	marp $(SLIDES) --watch --output $(OUT_DIR)/slides.html

$(OUT_DIR):
	mkdir -p $(OUT_DIR)

clean:
	rm -rf $(OUT_DIR)
