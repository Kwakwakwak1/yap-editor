.PHONY: sample transcribe plan cut render verify review quickstart clean

sample:
	@echo "python3 sample/make_sample.py"
	@python3 sample/make_sample.py

transcribe:
	@echo "mkdir -p build/sample && python3 pipeline/transcribe.py sample/sample-16x9.mp4 -o build/sample/A.words.json"
	@mkdir -p build/sample
	@python3 pipeline/transcribe.py sample/sample-16x9.mp4 -o build/sample/A.words.json

plan:
	@echo "mkdir -p build/sample && python3 pipeline/plan.py sample/sample.words.json -o build/sample/cuts.draft.json --media sample/sample-16x9.mp4"
	@mkdir -p build/sample
	@python3 pipeline/plan.py sample/sample.words.json -o build/sample/cuts.draft.json --media sample/sample-16x9.mp4

cut:
	@echo "python3 pipeline/assemble.py sample/cuts.json"
	@python3 pipeline/assemble.py sample/cuts.json

render:
	@echo "mkdir -p out && cd render && npx remotion render src/index.ts LandscapeOnBlack ../out/sample-reel.mp4 --props=public/reels/sample/props.json"
	@mkdir -p out
	@cd render && npx remotion render src/index.ts LandscapeOnBlack ../out/sample-reel.mp4 --props=public/reels/sample/props.json

verify:
	@echo "python3 pipeline/verify.py build/sample/cut.mp4"
	@python3 pipeline/verify.py build/sample/cut.mp4

review:
	@echo "python3 review/build.py --add out/sample-reel.mp4"
	@python3 review/build.py --add out/sample-reel.mp4

quickstart: cut render

clean:
	@echo "rm -rf build out"
	@rm -rf build out
