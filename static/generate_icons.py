# Icon Generation Script for Injaaz PWA
# This script generates all required PWA icon sizes from your logo.png

from PIL import Image
import os

# Icon sizes needed for PWA
SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

def generate_icons():
    """Generate PWA icons from logo.png"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(script_dir, 'logo.png')
    icons_dir = os.path.join(script_dir, 'icons')
    
    # Create icons directory
    os.makedirs(icons_dir, exist_ok=True)
    
    # Check if logo exists
    if not os.path.exists(logo_path):
        print(f"❌ Logo not found at: {logo_path}")
        print("Please place your logo.png in the static folder")
        return False
    
    try:
        # Open and prepare logo
        logo = Image.open(logo_path)
        
        # Convert to RGBA if needed
        if logo.mode != 'RGBA':
            logo = logo.convert('RGBA')
        
        print(f"📦 Original logo size: {logo.size}")
        print(f"🎨 Generating {len(SIZES)} icon sizes...")
        
        # Generate each size
        for size in SIZES:
            # Resize with high-quality resampling
            resized = logo.resize((size, size), Image.Resampling.LANCZOS)
            
            # Save icon
            output_path = os.path.join(icons_dir, f'icon-{size}x{size}.png')
            resized.save(output_path, 'PNG', optimize=True)
            print(f"  ✅ Generated: icon-{size}x{size}.png")
        
        # Generate maskable icons (with padding for safety zone)
        print("\n🎭 Generating maskable icons with safe zone...")
        for size in [192, 512]:
            # Create canvas with padding (80% of size)
            canvas_size = size
            logo_size = int(size * 0.8)
            padding = (canvas_size - logo_size) // 2
            
            # Create new image with transparent background
            canvas = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
            
            # Resize logo and paste on canvas
            resized_logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            canvas.paste(resized_logo, (padding, padding), resized_logo)
            
            # Save maskable icon
            output_path = os.path.join(icons_dir, f'icon-{size}x{size}-maskable.png')
            canvas.save(output_path, 'PNG', optimize=True)
            print(f"  ✅ Generated: icon-{size}x{size}-maskable.png")
        
        print(f"\n✨ Successfully generated all PWA icons in: {icons_dir}")
        return True
        
    except Exception as e:
        print(f"❌ Error generating icons: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("INJAAZ PWA ICON GENERATOR")
    print("=" * 60)
    print()
    
    success = generate_icons()
    
    print()
    print("=" * 60)
    if success:
        print("✅ ICON GENERATION COMPLETE!")
        print()
        print("Next steps:")
        print("1. Check static/icons/ folder for generated icons")
        print("2. Optionally replace with custom designs")
        print("3. Test PWA installation on mobile device")
    else:
        print("❌ ICON GENERATION FAILED")
        print()
        print("Please ensure:")
        print("1. PIL/Pillow is installed: pip install Pillow")
        print("2. logo.png exists in static/ folder")
    print("=" * 60)
