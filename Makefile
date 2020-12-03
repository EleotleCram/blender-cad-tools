

##############################################################################
# Note: This Makefile is only needed to maintain this public git repository. #
#                                                                            #
#             >>>>> Blender users should ignore this file <<<<<              #
#                                                                            #
##############################################################################

ADDONS=$(shell ls -d1 ../addons/* | cut -b 4-)

all: $(ADDONS)
	@echo "All done."

addons/%:
	git subtree add -P $@ ../$@ master
