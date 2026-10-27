import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def create_itinerary_card(output_path="sample_itinerary_card.png"):
    # 1. Canvas Dimensions
    width = 1080
    height = 1680
    
    # Fonts
    font_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    f_bold = lambda s: ImageFont.truetype(os.path.join(font_dir, "segoeuib.ttf"), s)
    f_reg = lambda s: ImageFont.truetype(os.path.join(font_dir, "segoeui.ttf"), s)
    f_semi = lambda s: ImageFont.truetype(os.path.join(font_dir, "segoeuisl.ttf"), s)
    
    # 2. Main Background (Soft warm modern background)
    base = Image.new("RGBA", (width, height), (242, 246, 246, 255))
    
    # Header Background (Deep Navy)
    header_height = 360
    header_img = Image.new("RGBA", (width, header_height), (11, 35, 69, 255))
    
    # Draw subtle gradient/glow inside header
    draw_h = ImageDraw.Draw(header_img)
    # Accent subtle decorative arc
    draw_h.ellipse([width - 250, -100, width + 300, 350], fill=(18, 59, 102, 140))
    draw_h.ellipse([-150, -80, 250, 260], fill=(15, 48, 88, 120))
    
    base.paste(header_img, (0, 0))
    
    # 3. Logo Placement (Top-Left)
    logo_path = "logo.png"
    if os.path.exists(logo_path):
        logo_img = Image.open(logo_path).convert("RGBA")
        logo_size = 84
        logo_img = logo_img.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        base.paste(logo_img, (60, 48), logo_img)
    
    draw = ImageDraw.Draw(base)
    
    # Brand Name and Tagline
    draw.text((160, 52), "DREAM DESTINY", font=f_bold(26), fill=(255, 255, 255, 255))
    draw.text((160, 90), "YOUR AI TRAVEL COMPANION", font=f_bold(13), fill=(94, 234, 212, 255))
    
    # Right Header Pill (Verified by Dream Destiny)
    pill_text = "✓ Verified Itinerary"
    p_box = [width - 290, 62, width - 60, 108]
    draw.rounded_rectangle(p_box, radius=23, fill=(18, 59, 102, 220), outline=(94, 234, 212, 120), width=1)
    draw.text((width - 268, 72), pill_text, font=f_bold(16), fill=(94, 234, 212, 255))
    
    # Hero Trip Title
    draw.text((60, 165), "3-Day Goa Coastal Escape", font=f_bold(44), fill=(255, 255, 255, 255))
    
    # Metadata Chips Row
    chips = [
        ("🗓️ 14 – 17 Nov", (20, 60, 105, 255), (255, 255, 255, 255)),
        ("👥 2 Travelers", (20, 60, 105, 255), (255, 255, 255, 255)),
        ("⚡ Relaxed Pace", (20, 60, 105, 255), (255, 255, 255, 255)),
        ("💰 ~₹14,500 Total", (16, 75, 60, 255), (167, 243, 208, 255))
    ]
    cur_x = 60
    for label, bg_col, text_col in chips:
        bbox = f_bold(16).getbbox(label)
        tw = bbox[2] - bbox[0]
        pad_x = 22
        chip_w = tw + pad_x * 2
        chip_box = [cur_x, 240, cur_x + chip_w, 292]
        draw.rounded_rectangle(chip_box, radius=26, fill=bg_col)
        draw.text((cur_x + pad_x, 252), label, font=f_bold(16), fill=text_col)
        cur_x += chip_w + 14

    # Helper function for card shadow & container
    def draw_card(y_top, c_height):
        card_box = [50, y_top, width - 50, y_top + c_height]
        # Shadow layer
        shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow)
        s_box = [52, y_top + 4, width - 48, y_top + c_height + 8]
        s_draw.rounded_rectangle(s_box, radius=24, fill=(13, 25, 40, 28))
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        base.alpha_composite(shadow)
        
        # Main white card
        d = ImageDraw.Draw(base)
        d.rounded_rectangle(card_box, radius=24, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=1)
        return card_box

    # 4. CARD 1: RECOMMENDED TRANSIT
    c1_y = 330
    c1_h = 240
    draw_card(c1_y, c1_h)
    
    # Card 1 Badge / Header
    draw.rounded_rectangle([80, c1_y + 24, 280, c1_y + 60], radius=18, fill=(238, 242, 255, 255))
    draw.text((96, c1_y + 31), "🚆 OUTBOUND RAIL", font=f_bold(14), fill=(67, 56, 202, 255))
    
    # Provider pill
    draw.rounded_rectangle([width - 240, c1_y + 24, width - 80, c1_y + 60], radius=18, fill=(254, 242, 242, 255))
    draw.text((width - 225, c1_y + 31), "ixigo live rates", font=f_bold(13), fill=(220, 38, 38, 255))
    
    # Train Name
    draw.text((80, c1_y + 80), "Mandovi Express (10103)", font=f_bold(26), fill=(13, 15, 16, 255))
    
    # Timings and Station
    draw.text((80, c1_y + 124), "07:10 AM CSMT (Mumbai)  ➔  06:45 PM Madgaon (Goa)", font=f_bold(18), fill=(55, 65, 81, 255))
    draw.text((80, c1_y + 154), "Travel Duration: 9h 35m • Scenic Konkan Railway Route", font=f_reg(16), fill=(107, 114, 128, 255))
    
    # Transit Meta Chips
    pills = [
        ("AC 3 Tier (3A)", (243, 244, 246, 255), (31, 41, 55, 255)),
        ("₹480 / person", (243, 244, 246, 255), (31, 41, 55, 255)),
        ("● AVL 24 Seats", (220, 252, 231, 255), (22, 101, 52, 255)),
        ("Daily Departure", (243, 244, 246, 255), (75, 85, 99, 255))
    ]
    px = 80
    for text, bg, fg in pills:
        tw = f_bold(14).getbbox(text)[2] - f_bold(14).getbbox(text)[0]
        pw = tw + 24
        draw.rounded_rectangle([px, c1_y + 190, px + pw, c1_y + 224], radius=17, fill=bg)
        draw.text((px + 12, c1_y + 196), text, font=f_bold(14), fill=fg)
        px += pw + 12

    # 5. CARD 2: RECOMMENDED HOTEL & STAY
    c2_y = 595
    c2_h = 240
    draw_card(c2_y, c2_h)
    
    draw.rounded_rectangle([80, c2_y + 24, 305, c2_y + 60], radius=18, fill=(236, 253, 245, 255))
    draw.text((96, c2_y + 31), "🏨 VERIFIED ACCOMMODATION", font=f_bold(14), fill=(5, 150, 105, 255))
    
    draw.rounded_rectangle([width - 250, c2_y + 24, width - 80, c2_y + 60], radius=18, fill=(240, 253, 250, 255))
    draw.text((width - 235, c2_y + 31), "Google Hotels verified", font=f_bold(13), fill=(13, 148, 136, 255))
    
    draw.text((80, c2_y + 80), "Fairfield by Marriott, Calangute", font=f_bold(26), fill=(13, 15, 16, 255))
    draw.text((80, c2_y + 124), "⭐ 4.4 / 5.0 (850+ reviews)  •  Calangute, North Goa", font=f_bold(18), fill=(55, 65, 81, 255))
    draw.text((80, c2_y + 154), "400m from Calangute Beach • Outdoor Pool • Free Breakfast Included", font=f_reg(16), fill=(107, 114, 128, 255))
    
    hotel_pills = [
        ("~₹4,200 / night", (243, 244, 246, 255), (31, 41, 55, 255)),
        ("3 Nights: ₹12,600", (243, 244, 246, 255), (31, 41, 55, 255)),
        ("Free Cancellation", (220, 252, 231, 255), (22, 101, 52, 255)),
        ("High Proximity to Sights", (243, 244, 246, 255), (75, 85, 99, 255))
    ]
    px = 80
    for text, bg, fg in hotel_pills:
        tw = f_bold(14).getbbox(text)[2] - f_bold(14).getbbox(text)[0]
        pw = tw + 24
        draw.rounded_rectangle([px, c2_y + 190, px + pw, c2_y + 224], radius=17, fill=bg)
        draw.text((px + 12, c2_y + 196), text, font=f_bold(14), fill=fg)
        px += pw + 12

    # 6. CARD 3: DAY-BY-DAY ITINERARY SCHEDULE
    c3_y = 860
    c3_h = 630
    draw_card(c3_y, c3_h)
    
    draw.rounded_rectangle([80, c3_y + 24, 340, c3_y + 60], radius=18, fill=(255, 247, 237, 255))
    draw.text((96, c3_y + 31), "📅 DAY-BY-DAY ITINERARY", font=f_bold(14), fill=(194, 65, 12, 255))
    
    draw.text((width - 290, c3_y + 31), "Synthesized by Amazon Bedrock", font=f_reg(13), fill=(156, 163, 175, 255))
    
    days_data = [
        (
            "DAY 1",
            (11, 35, 69, 255),
            "Arrival & North Goa Beaches",
            "14 Nov",
            [
                ("10:00 AM", "Arrival at Madgaon Station & scenic cab ride to Calangute"),
                ("01:30 PM", "Authentic Goan fish thali lunch at Fisherman's Wharf"),
                ("04:30 PM", "Sunset & evening ocean breeze at Curlies Beach Shack, Anjuna"),
                ("08:00 PM", "Stroll through the bustling Anjuna Flea Market & seaside dinner")
            ]
        ),
        (
            "DAY 2",
            (13, 148, 136, 255),
            "Heritage & Spice Plantation Safari",
            "15 Nov",
            [
                ("09:00 AM", "Explore UNESCO heritage sites: Basilica of Bom Jesus & Se Cathedral"),
                ("12:30 PM", "Sahakari Spice Plantation tour with traditional buffet lunch"),
                ("04:00 PM", "Heritage photo walk in Latin Quarter (Fontainhas, Panjim)"),
                ("07:30 PM", "Dinner & live fado music in the cobblestone streets of Panjim")
            ]
        ),
        (
            "DAY 3",
            (234, 88, 12, 255),
            "Water Adventures & Sunset River Cruise",
            "16 Nov",
            [
                ("08:30 AM", "Morning water sports at Baga Beach (Parasailing & Jet Ski)"),
                ("01:00 PM", "Beachside lunch & relaxed cocktails at Thalassa (Vagator)"),
                ("05:30 PM", "1-hour sunset cruise on Mandovi River with Goan folk performances"),
                ("08:30 PM", "Souvenir shopping in Mapusa market & departure transit prep")
            ]
        )
    ]
    
    day_y = c3_y + 80
    for tag, tag_col, title, date_str, activities in days_data:
        # Day Badge
        draw.rounded_rectangle([80, day_y, 155, day_y + 34], radius=17, fill=tag_col)
        draw.text((95, day_y + 6), tag, font=f_bold(14), fill=(255, 255, 255, 255))
        
        # Day Title
        draw.text((170, day_y + 4), title, font=f_bold(20), fill=(13, 15, 16, 255))
        draw.text((width - 160, day_y + 6), date_str, font=f_bold(15), fill=(107, 114, 128, 255))
        
        # Activities
        act_y = day_y + 44
        for t_time, desc in activities:
            # Bullet Dot
            draw.ellipse([84, act_y + 7, 92, act_y + 15], fill=tag_col)
            draw.text((104, act_y + 2), t_time, font=f_bold(14), fill=(55, 65, 81, 255))
            draw.text((195, act_y + 2), desc, font=f_reg(15), fill=(75, 85, 99, 255))
            act_y += 28
            
        # Divider line between days
        day_y = act_y + 16
        if tag != "DAY 3":
            draw.line([80, day_y - 8, width - 80, day_y - 8], fill=(241, 245, 249, 255), width=1)

    # 7. FOOTER BRAND BAR
    footer_y = 1520
    draw.rounded_rectangle([50, footer_y, width - 50, footer_y + 110], radius=24, fill=(11, 35, 69, 255))
    
    # Footer Text
    draw.text((80, footer_y + 26), "Plan, customize, and book your next trip directly in WhatsApp.", font=f_bold(18), fill=(255, 255, 255, 255))
    draw.text((80, footer_y + 58), "Message Dream Destiny to create your own personalized day-wise itinerary in seconds.", font=f_reg(14), fill=(156, 163, 175, 255))
    
    # WhatsApp Pill
    wa_box = [width - 280, footer_y + 32, width - 80, footer_y + 78]
    draw.rounded_rectangle(wa_box, radius=23, fill=(37, 211, 102, 255))
    draw.text((width - 250, footer_y + 44), "💬 Chat on WhatsApp", font=f_bold(15), fill=(255, 255, 255, 255))
    
    # Convert to RGB and save
    final_img = Image.new("RGB", (width, height), (242, 246, 246))
    final_img.paste(base, mask=base.split()[3])
    final_img.save(output_path, "PNG", quality=95)
    print(f"Successfully generated itinerary card: {output_path} ({width}x{height})")

if __name__ == "__main__":
    create_itinerary_card()
