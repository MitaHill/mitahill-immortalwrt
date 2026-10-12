<img src="https://avatars.githubusercontent.com/u/53193414?s=200&v=4" alt="logo" width="200" height="200" align="right">

# Project ImmortalWrt

ImmortalWrt is a fork of [OpenWrt](https://openwrt.org), with more packages ported, more devices supported, default optimized profiles and localization modifications for mainland China users.<br/>
Compared to upstream, we allow to use (non-upstreamable) modifications/hacks to provide better feature/performance/support.

This fork is based on ImmortalWrt 25.12.2 and provides AMD64 and ARM64 EFI firmware with PassWall and Bandix compiled from source.<br/>
It includes the required proxy cores, GeoIP/GeoSite data and disk utilities in the firmware, and adds offline automatic root partition and filesystem expansion for x86-64 ext4 images.
GitHub Actions workflows check the required packages, with an additional offline boot and expansion test for AMD64.

Default login address: http://192.168.1.1 or http://immortalwrt.lan, username: __root__, password: _none_.
