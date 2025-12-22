# Changelog

## [1.1.0](https://github.com/ddzero2c/tmux-easymotion/compare/v1.0.0...v1.1.0) (2025-12-19)


### Features

* easymotion-s2 mode ([#11](https://github.com/ddzero2c/tmux-easymotion/issues/11)) ([5937bbd](https://github.com/ddzero2c/tmux-easymotion/commit/5937bbd59e303538effbf4560bddfb534a2543de))

## 1.0.0 (2025-10-26)


### Features

* Add case-sensitive search option for tmux easymotion ([d475127](https://github.com/ddzero2c/tmux-easymotion/commit/d475127b541e1f927f56fb7eb1cd526d484a0502))
* Add coordinate conversion helper function ([2386adc](https://github.com/ddzero2c/tmux-easymotion/commit/2386adc456c827773095f1b7f9c106eb953785bb))
* Add curses support while maintaining ANSI sequence functionality ([626ec93](https://github.com/ddzero2c/tmux-easymotion/commit/626ec939b95feb7a8a68b0e352515551ce771c6d))
* Add detailed logging to pyshell function when debug environment variable is set ([30cecc3](https://github.com/ddzero2c/tmux-easymotion/commit/30cecc38906f120c89cea89b1d75a400d02c6582))
* Add logging to pyshell function ([e064edc](https://github.com/ddzero2c/tmux-easymotion/commit/e064edc8645cd2e96b4e3d6920e35e9a4bf39203))
* Add scroll position handling for cursor movement in copy-mode ([3adcb42](https://github.com/ddzero2c/tmux-easymotion/commit/3adcb42f3fe816be070bd23b85c9f4198649a25e))
* Add smartsign feature with shift symbol mapping ([b2bd3cf](https://github.com/ddzero2c/tmux-easymotion/commit/b2bd3cf7334583d0627c06032818eabca3e7efcd))
* Add support for double-width characters in easymotion ([1a78032](https://github.com/ddzero2c/tmux-easymotion/commit/1a780323c71696ef60a9bfac074220c154bf9884))
* Add support for multiple panes in easymotion.py ([9bdd712](https://github.com/ddzero2c/tmux-easymotion/commit/9bdd712c1d4a15bb44e0aed54a7595f3cfb56614))
* draw borders for panes ([6c120c7](https://github.com/ddzero2c/tmux-easymotion/commit/6c120c7ad40074bc3a8d0b2b5b3c795f28ce8f3b))
* Implement cursor-aware hint generation with distance-based sorting ([fbda3b3](https://github.com/ddzero2c/tmux-easymotion/commit/fbda3b30fb10b58558356912571856edbf04881a))
* Implement dynamic hint generation ([504311f](https://github.com/ddzero2c/tmux-easymotion/commit/504311fb4bca2a4ae4766476a65a41ddd67a438a))
* Improve README.md with better configuration and environment variable documentation ([62bb7bb](https://github.com/ddzero2c/tmux-easymotion/commit/62bb7bbfad5353936c2f528f72f9e7fb7c1b5629))
* Improve search input handling that should not missing a keystroke ([785f08c](https://github.com/ddzero2c/tmux-easymotion/commit/785f08c01e26592e6fed6186cd207ab5c2c5d84f))
* make hint color configurable ([ee8d8e4](https://github.com/ddzero2c/tmux-easymotion/commit/ee8d8e43f4de7fab1a18248f3f39741f4619547f))
* Optimize startup performance and reduce screen redraws ([ec7b3a8](https://github.com/ddzero2c/tmux-easymotion/commit/ec7b3a82c0a77ba44bacb76175424ecdef4c33b5))
* Replace curses with ANSI escape sequences for terminal control ([94f52dc](https://github.com/ddzero2c/tmux-easymotion/commit/94f52dc995494c9080ad7aadb0244b9756aaca39))


### Bug Fixes

* Add boundary checks and error handling to hint drawing in easymotion.py ([803c045](https://github.com/ddzero2c/tmux-easymotion/commit/803c04553b7c61af92bf513e698e4e25b3051a59))
* add smartsign ([9559366](https://github.com/ddzero2c/tmux-easymotion/commit/9559366f3f09320a4fbf410d3453380aa56e2406))
* draw hint ([8ff9e63](https://github.com/ddzero2c/tmux-easymotion/commit/8ff9e6343676222cd94987cee7f87e031d58caa1))
* escape hints ([56c6292](https://github.com/ddzero2c/tmux-easymotion/commit/56c62920021a77210ba162170624c22d777ce4c4))
* escape hints ([f299119](https://github.com/ddzero2c/tmux-easymotion/commit/f299119eb587fb1d5b1e873c1a52ae1296f5e938))
* first input is space ([f58f32b](https://github.com/ddzero2c/tmux-easymotion/commit/f58f32b62f309db39523e0805080ba234f141c5e)), closes [#2](https://github.com/ddzero2c/tmux-easymotion/issues/2)
* Fix string formatting issue in tmux_capture_pane function ([885d0a7](https://github.com/ddzero2c/tmux-easymotion/commit/885d0a74fd9636050c5b3161d3d3bee9771d0513))
* get pane id wrong when there's background pane ([6edb298](https://github.com/ddzero2c/tmux-easymotion/commit/6edb298e08b4efbfbf4775bd0bdc24e58f920afd))
* handle ctrl-c properly ([39dd9b0](https://github.com/ddzero2c/tmux-easymotion/commit/39dd9b0f08041e60485ad6b5f022da32aa280e57))
* handle no match case ([fb8a444](https://github.com/ddzero2c/tmux-easymotion/commit/fb8a4443a76eb06d6aa083193fa187303035d412))
* Handle wide characters in easymotion.py ([5aaec2f](https://github.com/ddzero2c/tmux-easymotion/commit/5aaec2f4dba90e07b3f4b1dd41395e1cd7c736a8))
* improve annoy blink ([d9b69ea](https://github.com/ddzero2c/tmux-easymotion/commit/d9b69eae3e8c611777b03d2b70f49f7414edc4fe))
* move between multiple panes ([2307c0e](https://github.com/ddzero2c/tmux-easymotion/commit/2307c0e319345f45dc44160bf7bd28c8709b1570))
* over-pane distance calculation ([4870904](https://github.com/ddzero2c/tmux-easymotion/commit/4870904e3174b172083fca5b23593e1b19f4b3d2))
* prevent infinite loop and handle out-of-range indices in match finding ([0a318d7](https://github.com/ddzero2c/tmux-easymotion/commit/0a318d7802c0ad7d29cbda5d620b04198ab53df8))
* Redraw complete hint in original position ([07b097d](https://github.com/ddzero2c/tmux-easymotion/commit/07b097db6bb392977dddd3fda404b1bd52fcbcca))
* save temporary keystroke file in tmp dir ([156ac98](https://github.com/ddzero2c/tmux-easymotion/commit/156ac9881c51b5605d57c47077c2d1dfbab5881c))
* save temporary keystroke file in tmp dir ([bf92fdb](https://github.com/ddzero2c/tmux-easymotion/commit/bf92fdbf341d205b2a2bbb2ae638f0d84c5738b1))
* syntax error for python3.8 ([9ee2a80](https://github.com/ddzero2c/tmux-easymotion/commit/9ee2a803c056843d8ef71fcd61f1ccc77ae342bc))
* tpm script ([be5f7f2](https://github.com/ddzero2c/tmux-easymotion/commit/be5f7f202c317d4999c53407365458596f3548ac))
* use same hints as vim-easymotion ([4e451be](https://github.com/ddzero2c/tmux-easymotion/commit/4e451be0d345ab3ec8078fbd8c81e972e50f99ff))
