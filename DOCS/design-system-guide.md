# Designia Design System Guide
*Premium AR Furniture Marketplace - Luxurious yet Playful*

## 🎨 Brand Positioning

Designia bridges the gap between luxury and accessibility in furniture shopping. Our design system reflects a premium marketplace that doesn't intimidate - sophisticated enough for design professionals, approachable enough for first-time furniture buyers.

**Core Brand Personality:**
- **Luxurious**: High-end, premium, sophisticated
- **Playful**: Approachable, delightful, human
- **Innovative**: AR-powered, cutting-edge, future-forward
- **Trustworthy**: Reliable, secure, professional

---

## 🎭 Design Philosophy

### Primary Principles

1. **Elevated Simplicity**: Premium doesn't mean complex. Every element should feel intentional and refined.

2. **Confident Playfulness**: Use subtle animations, friendly copy, and delightful micro-interactions without sacrificing sophistication.

3. **Spatial Awareness**: As an AR platform, our design should feel spacious and dimensional, with depth and breathing room.

4. **Trust Through Transparency**: Clear information hierarchy, honest imagery, and consistent feedback loops.

---

## 🌈 Color Palette

### Primary Colors

**Designia Deep** - `#1A1B2E`
- Main brand color for headers, navigation, and key CTAs
- Sophisticated navy that conveys trust and premium quality
- Usage: Primary buttons, navigation bars, headings

**Warm Ivory** - `#F8F6F0` 
- Primary background color
- Warm, inviting alternative to stark white
- Usage: Main backgrounds, card backgrounds

**Accent Gold** - `#D4AF37`
- Premium accent for highlights and special elements
- Sparingly used to maintain sophistication
- Usage: Premium badges, special offers, success states

### Secondary Colors

**Soft Sage** - `#9CAF88`
- Calming green for positive actions and confirmations
- Usage: Success messages, availability indicators, nature themes

**Dusty Rose** - `#D4A574`
- Warm, approachable accent
- Usage: Favorites, highlighted content, warm CTAs

**Cloud Gray** - `#E8E8EA`
- Neutral for borders, dividers, and subtle backgrounds
- Usage: Input borders, card separators, subtle sections

### Semantic Colors

**Success Green** - `#4CAF50`
- Clear success and confirmation states
- Usage: Order confirmations, successful uploads

**Warning Amber** - `#FF9800`
- Attention and warning states
- Usage: Low stock, pending reviews

**Error Red** - `#F44336`
- Error states and critical alerts
- Usage: Form errors, failed uploads

**Info Blue** - `#2196F3`
- Informational content and tips
- Usage: Help text, AR guidance, tips

---

## 📝 Typography

### Font Stack

**Primary Font: Inter**
- Clean, modern, highly readable
- Excellent for UI elements and body text
- Available weights: 300, 400, 500, 600, 700

**Secondary Font: Playfair Display**
- Elegant serif for premium headlines
- Used sparingly for impact
- Available weights: 400, 500, 600, 700

### Type Scale

```css
/* Headings */
.heading-xl: 48px / 56px, Playfair Display, Semi-bold
.heading-lg: 36px / 44px, Playfair Display, Semi-bold  
.heading-md: 24px / 32px, Inter, Semi-bold
.heading-sm: 20px / 28px, Inter, Medium

/* Body Text */
.body-lg: 18px / 28px, Inter, Regular
.body-md: 16px / 24px, Inter, Regular
.body-sm: 14px / 20px, Inter, Regular

/* UI Text */
.caption: 12px / 16px, Inter, Medium
.label: 14px / 20px, Inter, Medium
.button: 16px / 24px, Inter, Medium
```

---

## 🎪 Component Guidelines

### Buttons

**Primary Button**
- Background: Designia Deep (#1A1B2E)
- Text: Warm Ivory (#F8F6F0)
- Hover: 10% opacity overlay
- Border-radius: 8px
- Padding: 12px 24px
- Usage: Main actions (Add to Cart, Checkout, Sign Up)

**Secondary Button**
- Background: transparent
- Text: Designia Deep (#1A1B2E)
- Border: 2px solid Designia Deep
- Hover: Background Designia Deep, Text Warm Ivory
- Usage: Secondary actions (View Details, Learn More)

**Premium Button**
- Background: Gradient (Accent Gold to Dusty Rose)
- Text: Designia Deep
- Box-shadow: 0 4px 12px rgba(212, 175, 55, 0.3)
- Usage: Premium features, AR activation, special offers

### Cards

**Product Card**
```css
.product-card {
  background: #FFFFFF;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(26, 27, 46, 0.08);
  padding: 0;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.product-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(26, 27, 46, 0.12);
}
```

**Premium Card**
```css
.premium-card {
  background: linear-gradient(135deg, #F8F6F0 0%, #FFFFFF 100%);
  border: 1px solid #D4AF37;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(212, 175, 55, 0.15);
}
```

### Form Elements

**Input Fields**
```css
.input-field {
  background: #FFFFFF;
  border: 2px solid #E8E8EA;
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 16px;
  transition: border-color 0.2s ease;
}

.input-field:focus {
  border-color: #1A1B2E;
  outline: none;
  box-shadow: 0 0 0 3px rgba(26, 27, 46, 0.1);
}
```

---

## 📱 Mobile-Specific Guidelines

### Touch Targets
- Minimum 44px × 44px for all interactive elements
- 8px minimum spacing between touch targets
- Primary buttons: 48px minimum height

### Mobile Typography
- Increase line height by 20% for better readability
- Maximum 65 characters per line
- Use system fonts as fallback for performance

### Mobile Colors
- Ensure 4.5:1 contrast ratio minimum
- Test in bright sunlight conditions
- Consider dark mode alternatives

### AR Interface Considerations
- Semi-transparent overlays: rgba(26, 27, 46, 0.8)
- High contrast text for camera overlay
- Minimal UI during AR experience
- Large, easy-to-tap AR controls

---

## 💻 Web-Specific Guidelines

### Desktop Layouts
- Maximum content width: 1200px
- Grid system: 12 columns with 24px gutters
- Sidebar width: 280px
- Card hover states with subtle animations

### Navigation
```css
.main-navigation {
  background: #1A1B2E;
  height: 72px;
  border-bottom: 2px solid #D4AF37;
}

.nav-link {
  color: #F8F6F0;
  font-weight: 500;
  padding: 24px 20px;
  transition: color 0.2s ease;
}

.nav-link:hover {
  color: #D4AF37;
}
```

---

## ✨ Motion & Animation

### Micro-Interactions

**Hover Effects**
- Duration: 200ms
- Easing: ease-out
- Transform: translateY(-2px to -4px)

**Loading States**
- Skeleton screens with gentle shimmer
- Progress indicators with brand colors
- Smooth fade-ins for content

**Page Transitions**
- Smooth slide transitions between routes
- Fade overlays for modal dialogs
- Stagger animations for list items

### AR-Specific Animations
- Gentle bounce for object placement
- Pulse effect for interactive elements
- Smooth rotation for product viewing

---

## 🎯 Platform-Specific Adaptations

### iOS Guidelines
- Follow Human Interface Guidelines
- Use SF Pro font when Inter isn't available
- Native iOS navigation patterns
- Haptic feedback for AR interactions

### Android Guidelines
- Material Design 3 influence for familiar patterns
- Roboto font fallback
- Android-specific navigation gestures
- Consistent with Android AR conventions

### Web Guidelines
- Progressive enhancement approach
- Keyboard navigation support
- Screen reader accessibility
- WebGL considerations for AR features

---

## 🔍 Accessibility Standards

### Color Accessibility
- WCAG 2.1 AA compliance minimum
- Color-blind friendly palette
- Never rely on color alone for information

### Interaction Accessibility
- Keyboard navigation for all functions
- Screen reader support
- Voice control compatibility for AR features
- Alternative input methods

### Visual Accessibility
- Minimum 16px font size on mobile
- High contrast mode support
- Scalable text up to 200%
- Clear focus indicators

---

## 📐 Spacing & Layout System

### Spacing Scale (8px base)
```css
--space-xs: 4px;   /* Tight spacing */
--space-sm: 8px;   /* Small spacing */
--space-md: 16px;  /* Default spacing */
--space-lg: 24px;  /* Large spacing */
--space-xl: 32px;  /* Extra large spacing */
--space-2xl: 48px; /* Section spacing */
--space-3xl: 64px; /* Page spacing */
```

### Grid System
- Mobile: 4-column grid, 16px gutters
- Tablet: 8-column grid, 20px gutters  
- Desktop: 12-column grid, 24px gutters

---

## 🖼️ Imagery Guidelines

### Product Photography
- Clean, minimal backgrounds (preferably white or warm ivory)
- Multiple angles with consistent lighting
- High resolution for AR processing
- Lifestyle shots in premium, well-designed spaces

### Brand Photography
- Warm, natural lighting
- Premium home environments
- Diverse representation
- Authentic, unposed moments

### Iconography
- Consistent line weight (2px)
- Rounded corners (2px radius)
- Designia Deep color by default
- 24px × 24px standard size

---

## 🎪 Premium vs. Standard Elements

### When to Use Premium Styling
- Verified designer profiles
- Featured/promoted products
- Premium subscription features
- Special offers or limited editions
- AR visualization activation

### Premium Visual Cues
- Gold accent borders
- Subtle gradients
- Enhanced shadows
- Special badges/icons
- Animated elements

---

## 🧪 Testing & Validation

### Design QA Checklist
- [ ] Colors meet accessibility standards
- [ ] Typography scales properly across devices
- [ ] Touch targets meet minimum size requirements
- [ ] Animations perform smoothly on mid-range devices
- [ ] AR interface elements remain visible in various lighting
- [ ] Premium elements feel special but not overwhelming

### Browser Testing
- Chrome, Safari, Firefox, Edge latest versions
- iOS Safari, Android Chrome for mobile
- WebXR support for AR features
- Fallback experiences for unsupported browsers

---

## 🔄 Maintenance & Updates

### Regular Reviews
- Quarterly design system audits
- User feedback integration
- Accessibility compliance updates
- Performance optimization reviews

### Version Control
- Semantic versioning for design system updates
- Documentation of breaking changes
- Migration guides for major updates
- Component deprecation timeline

---

*This design system should evolve with user feedback and technological advances while maintaining the core brand identity of luxurious accessibility.*