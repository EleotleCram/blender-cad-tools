

##############################################################################
# Note: This Makefile is only needed to maintain this public git repository. #
#                                                                            #
#             >>>>> Blender users should ignore this file <<<<<              #
#                                                                            #
##############################################################################

ADDONS=$(shell ls -d1 ../addons/* | cut -b 4-)
ADDONS_UPDATE=$(addsuffix .update, $(ADDONS))

all: $(ADDONS) $(ADDONS_UPDATE)
	@echo "All done."

addons/%:
	git subtree add -P $@ ../$@ main

addons/%.update: addons/%
	GIT_EDITOR=/bin/cat git subtree pull  -P $< ../$< main

publish: all
	git push origin main

.PHONY: addons/%.update publish
