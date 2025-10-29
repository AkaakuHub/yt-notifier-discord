#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

/**
 * Sanitize filename by removing invalid characters
 */
function sanitizeFilename(filename) {
  return filename
    .replace(/[<>:"/\\|?*]/g, '') // Remove invalid Windows characters
    .replace(/\n/g, '') // Remove newlines
    .replace(/\r/g, '') // Remove carriage returns
    .replace(/\t/g, '') // Remove tabs
    .trim();
}

/**
 * Rename files for a single video directory
 */
function renameVideoFiles(videoDir) {
  const videoId = path.basename(videoDir);

  // Find the JSON metadata file
  const jsonFile = path.join(videoDir, `${videoId}.info.json`);

  if (!fs.existsSync(jsonFile)) {
    console.error(`JSON file not found: ${jsonFile}`);
    return false;
  }

  try {
    // Read and parse JSON metadata
    const metadata = JSON.parse(fs.readFileSync(jsonFile, 'utf8'));
    const videoTitle = metadata.title;

    if (!videoTitle) {
      console.error(`No title found in JSON: ${jsonFile}`);
      return false;
    }

    // Sanitize the title for filename
    const sanitizedTitle = sanitizeFilename(videoTitle);
    console.log(`Processing: ${videoId} -> "${sanitizedTitle}"`);

    // Files to rename
    const filesToRename = [
      { old: `${videoId}.mp4`, new: `${sanitizedTitle}.mp4` },
      { old: `${videoId}.webp`, new: `${sanitizedTitle}.webp` },
      { old: `${videoId}.info.json`, new: `${sanitizedTitle}.info.json` }
    ];

    let renamedCount = 0;

    // Rename each file if it exists
    for (const file of filesToRename) {
      const oldPath = path.join(videoDir, file.old);
      const newPath = path.join(videoDir, file.new);

      if (fs.existsSync(oldPath)) {
        // Check if target file already exists
        if (fs.existsSync(newPath)) {
          console.warn(`  ⚠️  Target file already exists, skipping: ${file.new}`);
          continue;
        }

        try {
          fs.renameSync(oldPath, newPath);
          console.log(`  ✅ Renamed: ${file.old} -> ${file.new}`);
          renamedCount++;
        } catch (error) {
          console.error(`  ❌ Failed to rename ${file.old}:`, error.message);
        }
      }
    }

    console.log(`  📊 Renamed ${renamedCount} files for video ${videoId}`);
    return renamedCount > 0;

  } catch (error) {
    console.error(`  ❌ Error processing ${videoId}:`, error.message);
    return false;
  }
}

/**
 * Main function
 */
function main() {
  const downloadsDir = path.join(__dirname, 'data', 'downloads');

  if (!fs.existsSync(downloadsDir)) {
    console.error(`Downloads directory not found: ${downloadsDir}`);
    process.exit(1);
  }

  console.log(`🚀 Starting video file renaming process...`);
  console.log(`📁 Target directory: ${downloadsDir}`);
  console.log('');

  // Get all video directories
  const videoDirs = fs.readdirSync(downloadsDir)
    .filter(item => {
      const itemPath = path.join(downloadsDir, item);
      return fs.statSync(itemPath).isDirectory();
    })
    .map(item => path.join(downloadsDir, item));

  if (videoDirs.length === 0) {
    console.log('No video directories found.');
    return;
  }

  console.log(`📹 Found ${videoDirs.length} video directories`);
  console.log('');

  let successCount = 0;
  let totalCount = 0;

  // Process each video directory
  for (const videoDir of videoDirs) {
    totalCount++;
    if (renameVideoFiles(videoDir)) {
      successCount++;
    }
    console.log(''); // Add spacing between videos
  }

  console.log(`✨ Processing complete!`);
  console.log(`📊 Results: ${successCount}/${totalCount} videos processed successfully`);

  if (successCount < totalCount) {
    console.log(`⚠️  Some videos had errors. Check the output above for details.`);
  }
}

// Run the script
if (require.main === module) {
  main();
}

module.exports = { renameVideoFiles, sanitizeFilename };