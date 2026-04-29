import matplotlib.pyplot as plt

# Replace with the path to your exported template image
img_path = "template_grid.png"  # <-- Change this to your image file

img = plt.imread(img_path)
fig, ax = plt.subplots()
ax.imshow(img)
coords = []


def onclick(event):
    if event.xdata is not None and event.ydata is not None:
        coords.append((event.xdata, event.ydata))
        print(f"Clicked: x={event.xdata:.2f}, y={event.ydata:.2f}")
        ax.plot(event.xdata, event.ydata, 'ro')
        fig.canvas.draw()

cid = fig.canvas.mpl_connect('button_press_event', onclick)
plt.title("Click on the 9 pink dots (left-to-right, top-to-bottom)")
plt.show()

print("All coordinates:", coords) 