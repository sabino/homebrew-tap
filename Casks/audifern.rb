cask "audifern" do
  version "0.8.2"
  sha256 "c62597aabb3827b356923daf71fd4341169bb9f8a439e75ac5fb4a220487e433"

  url "https://github.com/sabino/audifern/releases/download/v#{version}/Audifern-#{version}-macos-universal.dmg"
  name "Audifern"
  desc "Local Bluetooth controls for compatible hearing aids"
  homepage "https://github.com/sabino/audifern"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on macos: :sonoma

  app "Audifern.app"
end
