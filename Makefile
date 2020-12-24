

##############################################################################
# Note: This Makefile is only needed to maintain this public git repository. #
#                                                                            #
#             >>>>> Blender users should ignore this file <<<<<              #
#                                                                            #
##############################################################################

SHELL := /bin/bash

ADDONS=$(shell ls -d1 ../addons/* | cut -b 4-)
ADDONS_UPDATE=$(addsuffix .update, $(ADDONS))
ADDONS_CHANGELOG_UPDATE=$(addsuffix /CHANGELOG.md, $(ADDONS))

all: $(ADDONS) $(ADDONS_UPDATE) $(ADDONS_CHANGELOG_UPDATE)
	@echo "All done."

addons/%:
	git subtree add -P $@ ../$@ main

addons/%.update: addons/%
	GIT_EDITOR=/bin/cat git subtree pull  -P $< ../$< main

addons/%/CHANGELOG.md: addons/% FORCE
	@echo "Updating $@ ..."
	@(\
		echo -e "# $$(echo $* |\
			sed 's/_/ /g;s/\b\(.\)/\u\1/g' )\n\n## Changelog\n" ;\
		git log --pretty=format:"%h%x09%d%x20%s" |\
			grep $*.py: |\
			sed "s/.* $*.py: /   * /;s/.* Version bump to \(.*\)/\n\n### \1\n/";\
		echo ""\
	) |\
		sed '/^$$/N;/^\n$$/D' |\
		sed 's/\([^ :;.,]*_[^ :;.,]*\)/`\1`/g' > $@

changelogs: $(ADDONS_CHANGELOG_UPDATE)
	@echo "All changelogs done."

publish: all
	git push origin main

.PHONY: addons/%.update addons/%/CHANGELOG.md changelogs publish

FORCE:
