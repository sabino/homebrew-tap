cask "audifern" do
  version "0.8.3"
  sha256 "1df172ebbc109f06b5f9a4eaa75868fc526eed2068cc35868786c48cb76a7442"

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
